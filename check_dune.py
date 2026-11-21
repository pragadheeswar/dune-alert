import os
import time
import pathlib
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
URLS = [u.strip() for u in os.environ.get("CHECK_URLS", "").split(",") if u.strip()]

MOVIE_ID = "MV207332"  # Dune: Part Three on District
BOOK_LINK = "https://www.district.in/movies/dune-part-three-movie-tickets-in-chennai-MV207332"

ALERT_FLAG = pathlib.Path("alerting.flag")
STOP_FLAG = pathlib.Path("stopped.flag")
API = f"https://api.telegram.org/bot{TOKEN}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}


def send(msg):
    r = requests.post(f"{API}/sendMessage", data={"chat_id": CHAT_ID, "text": msg}, timeout=20)
    print("Telegram:", r.status_code, r.text[:200])


def stop_requested(since):
    """True if you sent 'stop' to the bot after alerting started."""
    try:
        data = requests.get(f"{API}/getUpdates", timeout=20).json()
    except Exception as e:
        print("getUpdates error:", e)
        return False
    for upd in data.get("result", []):
        msg = upd.get("message") or {}
        text = (msg.get("text") or "").strip().lower().lstrip("/")
        if (str(msg.get("chat", {}).get("id")) == CHAT_ID
                and msg.get("date", 0) >= since
                and text == "stop"):
            return True
    return False


def booking_open():
    for url in URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            continue
        print(f"{url} -> HTTP {r.status_code}, {len(r.text)} chars")
        if r.status_code == 200 and MOVIE_ID in r.text:
            return url
    return None


def main():
    if os.environ.get("TEST_MODE") == "true":
        send("✅ Test message: your Dune checker bot is working!")
        return

    if STOP_FLAG.exists():
        print("Stopped by user. Delete stopped.flag and alerting.flag to re-arm.")
        return

    if ALERT_FLAG.exists():
        since = int(ALERT_FLAG.read_text().split()[0])
        if stop_requested(since):
            STOP_FLAG.write_text(str(int(time.time())))
            send("🛑 OK, alerts stopped. Enjoy Dune: Part Three! 🍿")
        else:
            send(f"🔔 Reminder: Dune: Part Three booking is OPEN in Chennai!\n"
                 f"{BOOK_LINK}\n\nReply 'stop' to stop these alerts.")
        return

    url = booking_open()
    if url:
        ALERT_FLAG.write_text(f"{int(time.time())} {url}")
        send(f"🎬 Dune: Part Three booking just OPENED in Chennai!\n"
             f"{BOOK_LINK}\n\nI'll keep reminding you every ~10 min. "
             f"Reply 'stop' to stop.")
    else:
        print("Not available yet.")


if __name__ == "__main__":
    main()
