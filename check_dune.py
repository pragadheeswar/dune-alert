import os
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
CITY = os.environ.get("CITY", "chennai").strip().lower()

# Optional override (used by the GitHub workflow); otherwise built from CITY
URLS = [u.strip() for u in os.environ.get("CHECK_URLS", "").split(",") if u.strip()]
if not URLS:
    URLS = [f"https://www.district.in/movies/{CITY}-movie-tickets"]

MOVIE_ID = "MV207332"  # Dune: Part Three on District
BOOK_LINK = f"https://www.district.in/movies/dune-part-three-movie-tickets-in-{CITY}-MV207332"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


def send(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=20,
        )
        print("Telegram:", "sent" if r.ok else f"FAILED {r.status_code} {r.text[:200]}")
    except Exception as e:
        print("Telegram ERROR:", e)


def check_district():
    """Returns (result, detail). result is 'open', 'closed', 'blocked' or 'error'."""
    result, detail = "error", ""
    for url in URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
        except Exception as e:
            print(f"ERROR fetching {url}: {e}")
            result, detail = "error", str(e)[:150]
            continue
        if r.status_code != 200:
            print(f"BLOCKED: {url} -> HTTP {r.status_code}")
            result, detail = "blocked", f"HTTP {r.status_code}"
            continue
        print(f"OK: {url} -> HTTP 200, {len(r.text)} chars")
        return ("open" if MOVIE_ID in r.text else "closed"), ""
    return result, detail


def main():
    if os.environ.get("TEST_MODE") == "true":
        send(f"✅ Dune checker is set up! Watching: {CITY.title()}")
        return

    result, detail = check_district()

    if result == "open":
        send(f"🎬 Dune: Part Three booking is OPEN in {CITY.title()}!\n{BOOK_LINK}")
    elif result == "closed":
        print("Not open yet.")
    elif result == "blocked":
        print("Could not check: District blocked the request.")
        send(f"⚠️ District blocked the check ({CITY.title()}, {detail}). Will retry next time.")
    else:
        print("Could not check: connection error.")
        send(f"❌ Could not reach District ({CITY.title()}): {detail}")


if __name__ == "__main__":
    main()
