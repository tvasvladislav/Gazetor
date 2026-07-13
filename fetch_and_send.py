import os
import requests
import feedparser
from datetime import datetime
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
LLM_API_KEY = os.environ.get("LLM_API_KEY")  # ключ Google Gemini
CHANNELS = [c for c in os.environ.get("CHANNELS", "").split(",") if c.strip()]
RSSHUB_BASE = os.environ.get("RSSHUB_BASE", "https://rsshub.app")
MAX_POSTS_PER_CHANNEL = 8

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


def fetch_via_telegram_web(channel: str):
    """Основной способ: публичная веб-версия Telegram-канала (t.me/s/канал)."""
    url = f"https://t.me/s/{channel}"
    try:
        resp = requests.get(url, timeout=15, headers=BROWSER_HEADERS)
        resp.raise_for_status()
    except Exception as e:
        print(f"[t.me] Ошибка загрузки {channel}: {e}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    posts = []
    for msg in soup.select("div.tgme_widget_message_text"):
        text = msg.get_text(separator=" ", strip=True)
        if text:
            posts.append(text)
    return posts[-MAX_POSTS_PER_CHANNEL:]


def fetch_via_rsshub(channel: str):
    """Запасной способ: RSS-фид через RSSHub (может блокировать облачные IP)."""
    url = f"{RSSHUB_BASE}/telegram/channel/{channel}"
    try:
        resp = requests.get(url, timeout=20, headers=BROWSER_HEADERS)
        resp.raise_for_status()
    except Exception as e:
        print(f"[RSSHub] Ошибка загрузки {channel}: {e}")
        return []

    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        print(f"[RSSHub] Не удалось разобрать RSS для {channel}: {feed.bozo_exception}")
        return []

    posts = []
    for entry in feed.entries[:MAX_POSTS_PER_CHANNEL]:
        title = entry.get("title", "") or ""
        raw_summary = entry.get("summary", "") or entry.get("description", "") or ""
        text = BeautifulSoup(raw_summary, "html.parser").get_text(separator=" ", strip=True)
        combined = f"{title.strip()}. {text}" if title.strip() and title.strip() not in text else text
        combined = combined.strip()
        if combined:
            posts.append(combined)
    return posts


def fetch_channel_posts(channel: str):
    channel = channel.strip().lstrip("@")
    if not channel:
        return []
    posts = fetch_via_telegram_web(channel)
    if not posts:
        print(f"Основной способ не дал результата для {channel}, пробую RSSHub...")
        posts = fetch_via_rsshub(channel)
    return deduplicate_posts(posts)


def deduplicate_posts(posts):
    """Убирает повторы: Telegram часто отдаёт один и тот же пост дважды
    (полную версию и обрезанную с многоточием)."""
    seen_prefixes = set()
    result = []
    for p in posts:
        prefix = p[:80].strip()
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        result.append(p)
    return result


def collect_all_posts():
    all_posts = {}
    for ch in CHANNELS:
        posts = fetch_channel_posts(ch)
        if posts:
            all_posts[ch.strip().lstrip("@")] = posts
    return all_posts


def build_prompt(all_posts):
    parts = []
    for ch, posts in all_posts.items():
        parts.append(f"### Канал: {ch}")
        for p in posts:
            parts.append(f"- {p}")
    raw_text = "\n".join(parts)

    prompt = f"""Ты — ассистент в стиле Джарвис: нейтральный, лаконичный, официальный тон, обращение "сэр".

Ниже приведены последние посты из нескольких Telegram-каналов.

Задача:
1. Отбери только значимые новости. Игнорируй рекламу, розыгрыши, самопиар, малозначимые посты.
2. Объедини похожие новости из разных каналов, убери дубли.
3. Сохраняй строго нейтральную, фактическую точку зрения — без эмоциональных оценок и без принятия чьей-либо стороны.
4. Составь краткую сводку — не более 10 пунктов, каждый пункт 1-2 предложения.
5. В начале добавь короткое приветствие вида: "Сэр, сводка на {datetime.now().strftime('%H:%M')}."
6. Если значимых новостей нет — так и напиши одной строкой.

Посты:
{raw_text}

Выведи только готовую сводку, без пояснений от себя."""
    return prompt


def discover_gemini_model() -> str:
    """Спрашивает у Google, какие модели сейчас доступны для этого ключа,
    и выбирает подходящую — так скрипт не ломается, когда Google
    переименовывает или снимает с поддержки старые версии моделей."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={LLM_API_KEY}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    models = data.get("models", [])

    usable = [
        m["name"]  # формат: "models/gemini-2.5-flash"
        for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    if not usable:
        raise RuntimeError(f"Google не вернул ни одной модели с generateContent. Ответ: {data}")

    # предпочитаем быстрые модели ("flash"), избегаем экспериментальных/превью версий
    def score(name: str):
        n = name.lower()
        return (
            0 if "flash" in n else (1 if "pro" in n else 2),
            1 if ("preview" in n or "exp" in n or "thinking" in n) else 0,
            len(n),
        )

    usable.sort(key=score)
    return usable[0]


def summarize_with_gemini(prompt: str) -> str:
    model = discover_gemini_model()  # напр. "models/gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={LLM_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        # Новостной контент о войне/терроризме иначе часто блокируется фильтрами
        # безопасности по умолчанию, даже при чисто нейтральной суммаризации.
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ],
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    candidates = data.get("candidates") or []
    if not candidates:
        feedback = data.get("promptFeedback", {})
        raise RuntimeError(f"Gemini не вернул кандидатов. promptFeedback: {feedback}")

    finish_reason = candidates[0].get("finishReason")
    parts = candidates[0].get("content", {}).get("parts")
    if not parts:
        raise RuntimeError(f"Gemini вернул пустой ответ. finishReason: {finish_reason}")

    return parts[0]["text"].strip()


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for i in range(0, len(text), 40
