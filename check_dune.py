import os
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
URLS = [u.strip() for u in os.environ.get("CHECK_URLS", "").split(",") if u.strip()]

MOVIE_ID = "MV207332"  # Dune: Part Three on District
BOOK_LINK = "https://www.district.in/movies/dune-part-three-movie-tickets-in-chennai-MV207332"
WORKFLOW_FILE = "dune-check.yml"
API = f"https://api.telegram.org/bot{TOKEN}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}


def send(msg):
    r = requests.post(f"{API}/sendMessage", data={"chat_id": CHAT_ID, "text": msg}, timeout=20)
    print("Telegram:", r.status_code, r.text[:200])


def read_and_clear_messages():
    """Get new messages sent to the bot, then mark them as read."""
    try:
        updates = requests.get(f"{API}/getUpdates", timeout=20).json().get("result", [])
        if updates:
            requests.get(f"{API}/getUpdates",
                         params={"offset": updates[-1]["update_id"] + 1}, timeout=20)
        return [u.get("message") or {} for u in updates]
    except Exception as e:
        print("getUpdates error:", e)
        return []


def user_said_stop(messages):
    for m in messages:
        text = (m.get("text") or "").strip().lower().lstrip("/")
        if str(m.get("chat", {}).get("id")) == CHAT_ID and text == "stop":
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
            return True
    return False


def disable_workflow():
    repo = os.environ["GITHUB_REPOSITORY"]
    r = requests.put(
        f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/disable",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json"},
        timeout=20,
    )
    print("Disable workflow:", r.status_code)


def main():
    if os.environ.get("TEST_MODE") == "true":
        send("✅ Test message: your Dune checker bot is working!")
        return

    messages = read_and_clear_messages()

    if not booking_open():
        print("Not available yet.")
        return

    if user_said_stop(messages):
        send("🛑 OK, alerts stopped and the checker is switched off. Enjoy Dune! 🍿")
        disable_workflow()
        return

    send(f"🎬 Dune: Part Three booking is OPEN in Chennai!\n{BOOK_LINK}\n\n"
         f"I'll remind you every ~10 min. Reply 'stop' to stop.")


if __name__ == "__main__":
    main()
