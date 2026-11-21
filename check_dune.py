import os
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
URLS = [u.strip() for u in os.environ.get("CHECK_URLS", "").split(",") if u.strip()]

MOVIE_ID = "MV207332"  # Dune: Part Three on District
BOOK_LINK = "https://www.district.in/movies/dune-part-three-movie-tickets-in-chennai-MV207332"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}


def send(msg):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg},
        timeout=20,
    )
    print("Telegram:", r.status_code, r.text[:200])


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


def main():
    if os.environ.get("TEST_MODE") == "true":
        send("✅ Test message: your Dune checker bot is working!")
        return

    if booking_open():
        send(f"🎬 Dune: Part Three booking is OPEN in Chennai!\n{BOOK_LINK}")
    else:
        print("Not available yet.")


if __name__ == "__main__":
    main()
