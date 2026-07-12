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
    print("=" * 50)
    print(url)

    feed = feedparser.parse(url)

    print("Status:", feed.get("status"))
    print("Entries:", len(feed.entries))
    print("Bozo:", feed.bozo)

    if feed.bozo:
        print(feed.bozo_exception)

    if feed.entries:
        print("Первая запись:", feed.entries[0].title)
requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
    json={
        "chat_id": CHAT_ID,
        "text": text[:4000]
    }
)
