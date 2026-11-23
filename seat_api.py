import os
import re
import json
import time
import pathlib
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
TG = f"https://api.telegram.org/bot{TOKEN}"

# ===== Your settings =====
DEFAULT_ROWS = ["A", "B", "C", "D", "E", "F", "G"]  # used unless changed with /rows
MIN_SEATS = 1                                        # seats needed in one row to alert

# Seat checks (need guest token). Theater number = position in this list (1, 2, ...)
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

# Showtime checks (public page, no token): alert when a theater gets shows
SHOWTIME_CHECKS = [
    {
        "label": "Avengers: Doomsday – Seven Screen's – 19 Dec – English",
        "url": ("https://www.district.in/movies/avengers-doomsday-movie-tickets-in-chennai-MV176735"
                "?frmtid=Mm5dpqTqJz&fromdate=2026-12-19"),
        "theatre": "Seven Screen",
        "date": "2026-12-19",
        "lang": "English",
    },
    {
        "label": "Avengers: Doomsday – Seven Screen's – 20 Dec – English",
        "url": ("https://www.district.in/movies/avengers-doomsday-movie-tickets-in-chennai-MV176735"
                "?frmtid=Mm5dpqTqJz&fromdate=2026-12-20"),
        "theatre": "Seven Screen",
        "date": "2026-12-20",
        "lang": "English",
    },
]
# =========================

HERE = pathlib.Path(__file__).parent
GUEST_FILE = HERE / "guest_token.txt"   # saved by /token (only if District asks)
ROWS_FILE = HERE / "rows.json"          # saved by /rows

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


# ---------- Rows per theater (by number) ----------

def load_saved_rows():
    try:
        return json.loads(ROWS_FILE.read_text())
    except Exception:
        return {}


def rows_for(num):
    return load_saved_rows().get(str(num)) or DEFAULT_ROWS


def parse_rows(text):
    """'A-G' / 'A,B,C' / 'A-C,H' -> ['A','B','C',...]. Returns None if invalid."""
    rows = []
    for part in text.replace(" ", "").upper().split(","):
        if not part:
            continue
        m = re.fullmatch(r"([A-Z])-([A-Z])", part)
        if m:
            a, b = ord(m.group(1)), ord(m.group(2))
            if a > b:
                a, b = b, a
            rows += [chr(c) for c in range(a, b + 1)]
        elif re.fullmatch(r"[A-Z]{1,2}", part):
            rows.append(part)
        else:
            return None
    return list(dict.fromkeys(rows)) or None   # remove duplicates, keep order


def handle_rows_command(arg):
    usage = f"Send: /rows NUMBER ROWS  (e.g. /rows 1 A-G)\nTheaters: 1 to {len(SHOWS)}"
    parts = arg.split(maxsplit=1)
    if len(parts) < 2 or not parts[0].isdigit() or not 1 <= int(parts[0]) <= len(SHOWS):
        send("❌ " + usage)
        return

    num = int(parts[0])
    label = SHOWS[num - 1]["label"]
    saved = load_saved_rows()

    if parts[1].strip().lower() == "default":
        saved.pop(str(num), None)
        ROWS_FILE.write_text(json.dumps(saved))
        send(f"✅ Theater {num}: {label}\nBack to default rows: {', '.join(DEFAULT_ROWS)}")
        return

    rows = parse_rows(parts[1])
    if not rows:
        send("❌ Couldn't read those rows. Examples: A-G  or  A,B,C  or  A-C,H")
        return
    saved[str(num)] = rows
    ROWS_FILE.write_text(json.dumps(saved))
    send(f"✅ Theater {num}: {label}\nNow watching rows: {', '.join(rows)}")


# ---------- Telegram commands ----------

def read_commands():
    """Handles /token and /rows. Returns True if /status was asked."""
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
        elif cmd == "rows":
            handle_rows_command(arg)
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


# ---------- Showtime checks (public page, no token) ----------

def check_showtimes(s, chk):
    """Returns (status_text, alert_text_or_None)."""
    label = chk["label"]
    try:
        r = s.get(chk["url"], timeout=30)
    except Exception:
        return f"{label}: ❌ connection error", None
    if r.status_code != 200:
        return f"{label}: ⚠️ HTTP {r.status_code}", None

    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        return f"{label}: ❌ page data not found", None
    try:
        data = json.loads(m.group(1))
    except Exception:
        return f"{label}: ❌ unreadable page data", None

    found, seen = [], set()
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            info = item.get("cinemaInfo")
            sessions = item.get("sessions")
            if isinstance(info, dict) and isinstance(sessions, list):
                name = info.get("name", "")
                if chk["theatre"].lower() in name.lower():
                    for sess in sessions:
                        if not isinstance(sess, dict):
                            continue
                        if sess.get("showDate", str(sess.get("showTime", ""))[:10]) != chk["date"]:
                            continue
                        if chk["lang"] and chk["lang"].lower() != str(sess.get("lang", "")).lower():
                            continue
                        key = (name, sess.get("sid"))
                        if key in seen:
                            continue
                        seen.add(key)
                        found.append((name, sess))
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)

    if not found:
        print(f"{label}: no shows yet")
        return f"{label}: 🔍 no shows yet", None

    found.sort(key=lambda x: x[1].get("showTimeISO", ""))
    theatre_name = found[0][0]
    lines = [f"• {sess.get('showTimeText', '?')} – {sess.get('scrnFmt', '')} "
             f"({sess.get('avail', '?')}/{sess.get('total', '?')} seats free)"
             for _, sess in found]
    detail = "\n".join(lines)
    print(f"{label}: {len(found)} shows\n{detail}")
    alert = f"📅 Shows OPEN!\n{label}\n{theatre_name}\n{detail}\n\nBook: {chk['url']}"
    return f"{label}: ✅ {len(found)} shows open", alert


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


def check_show(s, num, show):
    """Returns (status_text, alert_text_or_None, error_code_or_None)."""
    label, body = show["label"], show["body"]
    watch = rows_for(num)
    title = f"{num}. {label}\n   Watching rows: {', '.join(watch)}"
    try:
        r = fetch_layout(s, body)
    except Exception:
        return f"{title}\n   ❌ connection error", None, "error"

    if r.status_code == 401:
        return f"{title}\n   🔑 needs guest token", None, "401"
    if r.status_code != 200:
        print(f"{label}: HTTP {r.status_code} {r.text[:150]}")
        return f"{title}\n   ⚠️ HTTP {r.status_code}", None, "http"

    try:
        rows, name, when = parse(r.json(), body, label)
    except Exception:
        return f"{title}\n   ❌ unexpected data", None, "data"

    lines, found = [], {}
    for row in watch:
        info = rows.get(row)
        if not info:
            lines.append(f"   Row {row}: not on seat map")
            continue
        avail = info["available"]
        lines.append(f"   Row {row}: {len(avail)} available")
        if len(avail) >= MIN_SEATS:
            found[row] = avail

    header = f"{name}" + (f" | {when}" if when else "")
    status_text = (f"{num}. {header}\n   Watching rows: {', '.join(watch)}\n"
                   + "\n".join(lines))
    print(status_text)

    alert = None
    if found:
        detail = "\n".join(f"Row {r}: seats {', '.join(seats)}" for r, seats in found.items())
        alert = f"🎟️ Seats OPEN in your rows!\n{header}\n{detail}\n\nBook: {book_link(body)}"
    return status_text, alert, None


def main():
    status = read_commands()   # applies /rows and /token before checking
    s = make_session()

    status_parts, errors = [], []

    # 1) Showtime checks (no token)
    for chk in SHOWTIME_CHECKS:
        status_text, alert = check_showtimes(s, chk)
        status_parts.append(status_text)
        if alert:
            send(alert)

    # 2) Seat checks: each theater with its own rows
    for num, show in enumerate(SHOWS, 1):
        status_text, alert, err = check_show(s, num, show)
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
