import os
import re
import time
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
CITY = os.environ.get("CITY", "chennai").strip().lower()

# Optional override (used by the GitHub workflow); otherwise built from CITY
URLS = [u.strip() for u in os.environ.get("CHECK_URLS", "").split(",") if u.strip()]
if not URLS:
    URLS = [f"https://www.district.in/movies/{CITY}-movie-tickets"]

MOVIE_ID = "MV207332"  # Dune: Part Three on District
MOVIE_PAGE = f"https://www.district.in/movies/dune-part-three-movie-tickets-in-{CITY}-MV207332"
API = f"https://api.telegram.org/bot{TOKEN}"

# Matches show formats like "IMAX 2D", "IMAX 3D", "IMAX 70MM", "IMAX Laser"
IMAX_PATTERN = re.compile(r"IMAX[\s\-]*(2D|3D|70\s?MM|LASER|WITH LASER)", re.IGNORECASE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

RESULT_TEXT = {
    "imax": "🎬 IMAX booking OPEN",
    "no_imax": "🟡 Booking open, but no IMAX shows yet",
    "closed": "🔍 Not open yet",
    "blocked": "⚠️ Blocked by District",
    "error": "❌ Connection error",
}


def send(msg):
    try:
        r = requests.post(f"{API}/sendMessage",
                          data={"chat_id": CHAT_ID, "text": msg}, timeout=20)
        print("Telegram:", "sent" if r.ok else f"FAILED {r.status_code} {r.text[:200]}")
    except Exception as e:
        print("Telegram ERROR:", e)


def fetch(url):
    """Returns (status, html_or_detail). status is 'ok', 'blocked' or 'error'."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
    except Exception as e:
        print(f"ERROR fetching {url}: {e}")
        return "error", str(e)[:150]
    if r.status_code != 200:
        print(f"BLOCKED: {url} -> HTTP {r.status_code}")
        return "blocked", f"HTTP {r.status_code}"
    print(f"OK: {url} -> HTTP 200, {len(r.text)} chars")
    return "ok", r.text


def check_district():
    """Returns (result, detail). result: imax, no_imax, closed, blocked, error."""
    # Step 1: is Dune in the city's bookable list?
    booking_open = False
    last_status, last_detail = "error", ""
    for url in URLS:
        status, data = fetch(url)
        if status != "ok":
            last_status, last_detail = status, data
            continue
        booking_open = MOVIE_ID in data
        last_status = "ok"
        break

    if last_status != "ok":
        return last_status, last_detail
    if not booking_open:
        return "closed", ""

    # Step 2: does the city's Dune page have IMAX shows?
    status, data = fetch(MOVIE_PAGE)
    if status != "ok":
        return status, data
    formats = sorted({m.group(0).upper() for m in IMAX_PATTERN.finditer(data)})
    if formats:
        print("IMAX formats found:", ", ".join(formats))
        return "imax", ", ".join(formats)
    return "no_imax", ""


def status_asked():
    """True if you sent /status since the last check. Marks messages as read."""
    try:
        updates = requests.get(f"{API}/getUpdates", timeout=20).json().get("result", [])
        if updates:
            requests.get(f"{API}/getUpdates",
                         params={"offset": updates[-1]["update_id"] + 1}, timeout=20)
    except Exception as e:
        print("getUpdates error:", e)
        return False
    for upd in updates:
        msg = upd.get("message") or {}
        text = (msg.get("text") or "").strip().lower().lstrip("/")
        if str(msg.get("chat", {}).get("id")) == CHAT_ID and text == "status":
            return True
    return False


def main():
    if os.environ.get("TEST_MODE") == "true":
        send(f"✅ Dune IMAX checker is set up! Watching: {CITY.title()}")
        return

    result, detail = check_district()

    if result == "imax":
        send(f"🎬 Dune: Part Three IMAX booking is OPEN in {CITY.title()}!\n"
             f"Formats: {detail}\n{MOVIE_PAGE}")
    elif result == "no_imax":
        print("Booking open, but no IMAX shows yet.")
    elif result == "closed":
        print("Not open yet.")
    elif result == "blocked":
        print("Could not check: District blocked the request.")
        send(f"⚠️ District blocked the check ({CITY.title()}, {detail}). Will retry next time.")
    else:
        print("Could not check: connection error.")
        send(f"❌ Could not reach District ({CITY.title()}): {detail}")

    if status_asked():
        now = time.strftime("%d-%m %H:%M")
        send(f"✅ Checker is running\nCity: {CITY.title()}\nChecked: {now}\n"
             f"Result: {RESULT_TEXT[result]}")


if __name__ == "__main__":
    main()

