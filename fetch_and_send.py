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


def fetch_channel_posts(channel: str):
    """Забирает последние посты канала через RSSHub (RSS-фид Telegram-канала)."""
    channel = channel.strip().lstrip("@")
    if not channel:
        return []
    url = f"{RSSHUB_BASE}/telegram/channel/{channel}"
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"Ошибка загрузки RSS для {channel}: {e}")
        return []

    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        print(f"Не удалось разобрать RSS для {channel}: {feed.bozo_exception}")
        return []

    posts = []
    for entry in feed.entries[:MAX_POSTS_PER_CHANNEL]:
        title = entry.get("title", "") or ""
        raw_summary = entry.get("summary", "") or entry.get("description", "") or ""
        text = BeautifulSoup(raw_summary, "html.parser").get_text(separator=" ", strip=True)
        if title and title.strip() and title.strip() not in text:
            combined = f"{title.strip()}. {text}"
        else:
            combined = text
        combined = combined.strip()
        if combined:
            posts.append(combined)
    return posts


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


def summarize_with_gemini(prompt: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={LLM_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):
        chunk = text[i:i + 4000]
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": chunk})
        if not r.ok:
            print("Ошибка отправки в Telegram:", r.text)


def main():
    all_posts = collect_all_posts()
    if not all_posts:
        send_telegram_message("Сэр, за прошедший период новых постов не обнаружено (или источники недоступны).")
        return

    prompt = build_prompt(all_posts)

    if LLM_API_KEY:
        try:
            summary = summarize_with_gemini(prompt)
        except Exception as e:
            print(f"Ошибка суммаризации: {e}")
            summary = "Сэр, не удалось сформировать сводку через ИИ. Ниже — необработанные заголовки.\n\n" + build_prompt(all_posts)
    else:
        summary = build_prompt(all_posts)

    send_telegram_message(summary)


if __name__ == "__main__":
    main()
