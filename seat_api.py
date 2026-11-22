import os
import re
import json
import time
import pathlib
from datetime import datetime
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
TG = f"https://api.telegram.org/bot{TOKEN}"

# ===== Your settings =====
WATCH_ROWS = ["A", "B", "C", "D", "E", "F", "G" , "Q"]   # alert if any seat opens in these rows
MIN_SEATS = 1                                       # seats needed in one row to alert

SHOWS = [
    {
        "label": "PVR Palazzo, Nexus Vijaya Mall (IMAX 2D)",
        "body": {
            "cinemaId": 1022274,
            "sessionId": "41457",
            "providerId": 1707,
            "screenOnTop": True,
            "freeSeating": False,
            "screenFormat": "IMAX 2D",
            "moviecode": "OBEXKD",
            "config": {"socialDistancing": 1},
            "contentId": "207332",
            "cityKey": "chennai",
            "sessionDate": "2026-12-16",
            "fetchSessions": True,
            "movieFormatCode": "6qgsw71c3s",
        },
    },
    {
        "label": "Theater 2 (IMAX 2D)",   # change to the real theater name if you like
        "body": {
            "cinemaId": 1020779,
            "sessionId": "69746",
            "providerId": 2624,
            "screenOnTop": True,
            "freeSeating": False,
            "screenFormat": "IMAX 2D",
            "moviecode": "OBEXKD",
            "config": {"socialDistancing": 1},
            "contentId": "207332",
        },
    },
]

# Alert when this theater has Dune shows on this date (no token needed)
DATE_CHECK = {
    "theatre": "Palazzo",      # part of the theater name
    "date": "2026-12-19",      # YYYY-MM-DD
    "format": "",              # "" = any format, or e.g. "IMAX"
}
# =========================

HERE = pathlib.Path(__file__).parent
GUEST_FILE = HERE / "guest_token.txt"   # saved by /token (only if District asks)

SEAT_API = ("https://www.district.in/gw/consumer/movies/v1/select-seat"
            "?version=3&site_id=1&channel=mweb&child_site_id=1&platform=district")
MOVIE_PAGE = "https://www.district.in/movies/dune-part-three-movie-tickets-in-chennai-MV207332"
USER_AGENT = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")


def send(msg):
    try:
        r = requests.post(f"{TG}/sendMessage",
                          data={"chat_id": CHAT_ID, "text": msg[:4000]}, timeout=20)
        print("Telegram:", "sent" if r.ok else f"FAILED {r.status_code} {r.text[:200]}")
    except Exception as e:
        print("Telegram ERROR:", e)


def get_guest_token():
    if GUEST_FILE.exists() and GUEST_FILE.read_text().strip():
        return GUEST_FILE.read_text().strip()
    return os.environ.get("GUEST_TOKEN", "").strip()


def read_commands():
    """Handles /token. Returns True if /status was asked. Marks messages as read."""
    try:
        updates = requests.get(f"{TG}/getUpdates", timeout=20).json().get("result", [])
        if updates:
            requests.get(f"{TG}/getUpdates",
                         params={"offset": updates[-1]["update_id"] + 1}, timeout=20)
    except Exception as e:
        print("getUpdates error:", e)
        return False

    status = False
    for upd in updates:
        msg = upd.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != CHAT_ID:
            continue
        cmd, _, arg = (msg.get("text") or "").strip().partition(" ")
        cmd, arg = cmd.lower().lstrip("/"), arg.strip()
        if cmd == "status":
            status = True
        elif cmd == "token":
            if arg:
                GUEST_FILE.write_text(arg)
                send("✅ Guest token saved.")
            else:
                send("❌ Send: /token VALUE")
    return status


def make_session():
    s = requests.Session()
    s.headers.update({"user-agent": USER_AGENT, "accept-language": "en-IN,en;q=0.9"})
    try:
        s.get("https://www.district.in/movies/", timeout=20)  # collect normal site cookies
    except Exception:
        pass
    print("Guest cookie from site:", "yes" if s.cookies.get("x-guest-token") else "no")
    guest = get_guest_token()
    if guest:
        s.cookies.set("x-guest-token", guest, domain="www.district.in")
    return s


# ---------- Date check (public page, no token) ----------

def find_shows(html):
    """All shows (ScreeningEvent) from the page's structured data."""
    shows = []
    blocks = re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S)
    for block in blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if item.get("@type") == "ScreeningEvent":
                    loc = item.get("location") or {}
                    shows.append({
                        "name": item.get("name", ""),
                        "start": item.get("startDate", ""),
                        "theatre": loc.get("name", "") if isinstance(loc, dict) else "",
                    })
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
    return shows


def check_date(s):
    """Returns (status_text, alert_text_or_None)."""
    theatre, date, fmt = DATE_CHECK["theatre"], DATE_CHECK["date"], DATE_CHECK["format"]
    title = f"{theatre} on {date}" + (f" ({fmt})" if fmt else "")
    url = f"{MOVIE_PAGE}?fromdate={date}"
    try:
        r = s.get(url, timeout=30)
    except Exception:
        return f"{title}: ❌ connection error", None
    if r.status_code != 200:
        return f"{title}: ⚠️ HTTP {r.status_code}", None

    found = []
    for show in find_shows(r.text):
        if theatre.lower() not in show["theatre"].lower():
            continue
        if not show["start"].startswith(date):
            continue
        if fmt and fmt.lower() not in show["name"].lower():
            continue
        found.append(show)

    if not found:
        print(f"{title}: no shows yet")
        return f"{title}: 🔍 no shows yet", None

    found.sort(key=lambda x: x["start"])
    lines = []
    for show in found:
        try:
            when = datetime.fromisoformat(show["start"]).strftime("%I:%M %p")
        except Exception:
            when = show["start"]
        m = re.search(r"\(([^)]*)\)\s*$", show["name"])
        lines.append(f"• {when} – {m.group(1) if m else 'show'}")
    detail = "\n".join(lines)
    print(f"{title}: {len(found)} shows\n{detail}")
    alert = (f"📅 Booking OPEN: {found[0]['theatre']} on {date}!\n{detail}\n\nBook: {url}")
    return f"{title}: ✅ {len(found)} shows open", alert


# ---------- Seat checks (need guest token) ----------

def fetch_layout(s, body):
    headers = {
        "accept": "*/*",
        "content-type": "application/json; charset=utf-8",
        "api_source": "district",
        "x-app-type": "ed_mweb",
        "origin": "https://www.district.in",
        "referer": MOVIE_PAGE,
    }
    return s.post(SEAT_API, headers=headers, data=json.dumps(body), timeout=30)


def parse(data, body, label):
    rows = {}
    for area in data["seatLayout"]["colAreas"]["objArea"]:
        for row in area.get("objRow", []):
            rid = (row.get("PhyRowId") or "").upper()
            if not rid:
                continue
            info = rows.setdefault(rid, {"available": [], "taken": 0})
            for seat in row.get("objSeat", []):
                if str(seat.get("SeatStatus")) == "0":
                    info["available"].append(seat.get("displaySeatNumber") or str(seat.get("seatNumber")))
                else:
                    info["taken"] += 1

    cinema = data.get("cinemaInfo") or {}
    name = (cinema.get("cinemaInfo") or {}).get("name") or label
    session = next((x for x in cinema.get("sessions") or []
                    if x.get("sid") == str(body["sessionId"])), {})
    when = session.get("show_time_ist", "")[:16].replace("T", " ")
    return rows, name, when


def book_link(body):
    if body.get("movieFormatCode") and body.get("sessionDate"):
        return f"{MOVIE_PAGE}?frmtid={body['movieFormatCode']}&fromdate={body['sessionDate']}"
    return MOVIE_PAGE


def check_show(s, show):
    """Returns (status_text, alert_text_or_None, error_code_or_None)."""
    label, body = show["label"], show["body"]
    try:
        r = fetch_layout(s, body)
    except Exception:
        return f"{label}: ❌ connection error", None, "error"

    if r.status_code == 401:
        return f"{label}: 🔑 needs guest token", None, "401"
    if r.status_code != 200:
        print(f"{label}: HTTP {r.status_code} {r.text[:150]}")
        return f"{label}: ⚠️ HTTP {r.status_code}", None, "http"

    try:
        rows, name, when = parse(r.json(), body, label)
    except Exception:
        return f"{label}: ❌ unexpected data", None, "data"

    lines, found = [], {}
    for row in WATCH_ROWS:
        info = rows.get(row)
        if not info:
            lines.append(f"  Row {row}: not on seat map")
            continue
        avail = info["available"]
        lines.append(f"  Row {row}: {len(avail)} available")
        if len(avail) >= MIN_SEATS:
            found[row] = avail

    header = f"{name}" + (f" | {when}" if when else "")
    status_text = header + "\n" + "\n".join(lines)
    print(status_text)

    alert = None
    if found:
        detail = "\n".join(f"Row {r}: seats {', '.join(seats)}" for r, seats in found.items())
        alert = f"🎟️ Seats OPEN in your rows!\n{header}\n{detail}\n\nBook: {book_link(body)}"
    return status_text, alert, None


def main():
    status = read_commands()
    s = make_session()

    status_parts, errors = [], []

    # 1) Date check: PVR Palazzo on 19 Dec
    date_status, date_alert = check_date(s)
    status_parts.append(date_status)
    if date_alert:
        send(date_alert)

    # 2) Seat checks: rows A–G at both theaters
    for show in SHOWS:
        status_text, alert, err = check_show(s, show)
        status_parts.append(status_text)
        if alert:
            send(alert)
        if err:
            errors.append((show["label"], err))

    if any(err == "401" for _, err in errors):
        send("🔑 District needs a guest token. Send: /token VALUE\n"
             "(PC Chrome → F12 → Application → Cookies → www.district.in → x-guest-token)")
    for label, err in errors:
        if err in ("http", "error", "data"):
            send(f"⚠️ Seat check failed for {label} ({err}). Will retry next time.")

    if status:
        send(f"✅ Seat checker is running ({time.strftime('%d-%m %H:%M')})\n\n"
             + "\n\n".join(status_parts))


if __name__ == "__main__":
    main()
