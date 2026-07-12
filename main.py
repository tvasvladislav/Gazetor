import os
import feedparser
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

feeds = [
    "https://rsshub.app/telegram/channel/odessa_infonews",
    "https://rsshub.app/telegram/channel/truexanewsua",
    "https://rsshub.app/telegram/channel/slav_kram",
    "https://rsshub.app/telegram/channel/hiaimedia",
]

text = "📰 Gazetor\n\n"

for url in feeds:
    feed = feedparser.parse(url)

    if feed.entries:
        news = feed.entries[0]

        title = news.title if hasattr(news, "title") else "Без заголовка"

        text += f"• {title}\n\n"
    else:
        text += f"• Не удалось получить новости:\n{url}\n\n"

requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
    json={
        "chat_id": CHAT_ID,
        "text": text[:4000]
    }
)
