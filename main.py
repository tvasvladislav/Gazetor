import os
import requests
import feedparser

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

feeds = [
    "https://rsshub.app/telegram/channel/odessa_infonews",
    "https://rsshub.app/telegram/channel/truexanewsua",
    "https://rsshub.app/telegram/channel/slav_kram",
    "https://rsshub.app/telegram/channel/hiaimedia",
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0 Safari/537.36"
}

text = "📰 Gazetor\n\n"

for url in feeds:
    print("=" * 50)
    print(url)

    r = requests.get(url, headers=headers, timeout=30)

    print("HTTP:", r.status_code)

    if r.status_code != 200:
        text += f"❌ {url}\nHTTP {r.status_code}\n\n"
        continue

    feed = feedparser.parse(r.text)

    print("Entries:", len(feed.entries))

    if feed.entries:
        text += "• " + feed.entries[0].title + "\n\n"
    else:
        text += f"❌ Нет записей: {url}\n\n"

requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
    json={
        "chat_id": CHAT_ID,
        "text": text[:4000]
    }
)
