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
    """Returns (status_text, alert_text_or_None, problem_or_None).
    problem is only set for things you should be told about:
    'token' (401), 'connection', 'blocked' (403)."""
    label, body = show["label"], show["body"]
    watch = rows_for(num)
    title = f"{num}. {label}\n   Watching rows: {',
