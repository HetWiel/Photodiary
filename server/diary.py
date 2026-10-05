# The photodiary of hetwiel.dev.
#
# Two things in one small program:
#
# 1. An upload endpoint (port 8080, via Caddy on upload.hetwiel.dev) the phone sends photos to.
#      POST /photo    the photo itself as the body, with "Authorization: Bearer <UPLOAD_TOKEN>"
#      POST /undo     takes the most recently sent photo out of the queue again
#      GET  /status   how many photos are waiting and when the next one appears
#      GET  /health   liveness check, no token needed
#    A photo is checked right away (no face?). Rejected = deleted immediately.
#
# 2. A daily round (PUBLISH_AT, Amsterdam time). It takes the oldest photo that has been
#    in the queue for at least MIN_WAIT_HOURS, checks it again, develops it and picks
#    a record from the crate. Together they become one entry in /public/index.json.
#    The original is then deleted. No photo that day? Then just the record.
#
# Caddy serves /public as photodiary.hetwiel.dev/data/. The site (site/) reads index.json there.

import hmac
import json
import os
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import crate
import migrate
import photo

TZ = ZoneInfo(os.environ.get("TZ", "Europe/Amsterdam"))
TOKEN = os.environ.get("UPLOAD_TOKEN", "")
DISCOGS_USER = os.environ.get("DISCOGS_USER", "")
DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN") or None
PUBLISH_AT = os.environ.get("PUBLISH_AT", "00:10")
MIN_WAIT = float(os.environ.get("MIN_WAIT_HOURS", "24")) * 3600
MAX_BYTES = 40 * 1024 * 1024

DATA = os.environ.get("DATA", "/data")
PUBLIC = os.environ.get("PUBLIC", "/public")
QUEUE = os.path.join(DATA, "queue")
STATE = os.path.join(DATA, "state.json")
INDEX = os.path.join(PUBLIC, "index.json")
PHOTOS = os.path.join(PUBLIC, "photos")

lock = threading.Lock()


def log(*a):
    print(datetime.now(TZ).strftime("%Y-%m-%d %H:%M"), *a, flush=True)


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def waiting():
    """Photos in the queue, oldest first. The name starts with the moment it was sent."""
    return sorted(n for n in os.listdir(QUEUE) if not n.startswith("."))


def received(name):
    return datetime.strptime(name[:15], "%Y%m%dT%H%M%S").replace(tzinfo=TZ).timestamp()


def next_round(after: datetime) -> datetime:
    h, m = (int(x) for x in PUBLISH_AT.split(":"))
    t = after.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if t > after else t + timedelta(days=1)


# ── The daily round ──────────────────────────────────────────────────

def publish(day: date):
    with lock:
        index = load(INDEX, [])
        if any(d["date"] == day.isoformat() for d in index):
            return
        state = load(STATE, {"played": []})

        entry_photo = None
        for name in waiting():
            if time.time() - received(name) < MIN_WAIT:
                break
            path = os.path.join(QUEUE, name)
            try:
                with open(path, "rb") as f:
                    img = photo.open_photo(f.read())
                photo.check(img)
                large, small = photo.develop(img, seed=day.toordinal())
                info = photo.details(img)
            except photo.Rejected as e:
                log("rejected at publishing:", name, e)
                os.remove(path)
                continue
            os.makedirs(PHOTOS, exist_ok=True)
            d = day.isoformat()
            large.save(os.path.join(PHOTOS, f"{d}.webp"), "WEBP", quality=80, method=6)
            small.save(os.path.join(PHOTOS, f"{d}-small.webp"), "WEBP", quality=78, method=6)
            entry_photo = {"src": f"photos/{d}.webp", "small": f"photos/{d}-small.webp",
                           "width": large.width, "height": large.height, **info}
            os.remove(path)  # the original, with all its metadata, is gone
            break

        record = None
        if DISCOGS_USER:
            records = crate.collection(DATA, DISCOGS_USER, DISCOGS_TOKEN)
            record, state["played"] = crate.pick(records, state["played"])
            if record:
                record = {**record, "link": f"https://www.discogs.com/release/{record['id']}",
                          "sound": crate.sound(record, DISCOGS_TOKEN)}

        if not entry_photo and not record:
            log("nothing to publish for", day)
            return
        index.insert(0, {"date": day.isoformat(), "photo": entry_photo, "record": record})
        index.sort(key=lambda d: d["date"], reverse=True)
        save(INDEX, index)
        save(STATE, state)
        log("published:", day, "photo" if entry_photo else "no photo", "+",
            record["artist"] + " – " + record["title"] if record else "no record")


def clock():
    # On start-up: has today's round happened yet? If not, and the time has passed, do it now.
    now = datetime.now(TZ)
    h, m = (int(x) for x in PUBLISH_AT.split(":"))
    if now.replace(hour=h, minute=m, second=0, microsecond=0) <= now:
        try:
            publish(now.date())
        except Exception as e:
            log("error in round:", repr(e))
    while True:
        t = next_round(datetime.now(TZ))
        while (wait := (t - datetime.now(TZ)).total_seconds()) > 0:
            time.sleep(min(wait, 300))
        try:
            publish(t.date())
        except Exception as e:
            log("error in round:", repr(e))


# ── The upload endpoint ──────────────────────────────────────────────

class Upload(BaseHTTPRequestHandler):
    server_version = "photodiary"
    sys_version = ""

    def log_message(self, fmt, *args):  # no IP addresses in the logs
        pass

    def reply(self, code, text):
        body = (text + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def authorised(self):
        if not TOKEN:
            self.reply(503, "Upload is not set up (no UPLOAD_TOKEN).")
            return False
        header = self.headers.get("Authorization", "")
        if not hmac.compare_digest(header.encode(), f"Bearer {TOKEN}".encode()):
            time.sleep(1)
            self.reply(401, "No.")
            return False
        return True

    def read_body(self):
        """The body, with or without Content-Length (some apps send it chunked)."""
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            parts, total = [], 0
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    self.rfile.readline()
                    break
                total += size
                if total > MAX_BYTES:
                    return None
                parts.append(self.rfile.read(size))
                self.rfile.readline()
            return b"".join(parts)
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BYTES:
            return None
        return self.rfile.read(length)

    def summary(self):
        n = len(waiting())
        upcoming = next_round(datetime.now(TZ)).strftime("%a %d %b, %H:%M")
        return f"{n} waiting. Next round: {upcoming}."

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, "ok")
        if self.path == "/status":
            if self.authorised():
                self.reply(200, self.summary())
            return
        self.reply(404, "Not here.")

    def do_POST(self):
        if self.path not in ("/photo", "/undo"):
            return self.reply(404, "Not here.")
        if not self.authorised():
            return
        if self.path == "/undo":
            with lock:
                queue = waiting()
                if not queue:
                    return self.reply(200, "Queue is empty.")
                os.remove(os.path.join(QUEUE, queue[-1]))
            return self.reply(200, "Last photo removed. " + self.summary())

        data = self.read_body()
        if not data:
            return self.reply(413, "Too large or empty.")
        try:
            img = photo.open_photo(data)
            photo.check(img)
        except photo.Rejected as e:
            return self.reply(422, f"Not accepted: {e}. Nothing was kept.")
        name = datetime.now(TZ).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4)
        with lock:
            with open(os.path.join(QUEUE, "." + name), "wb") as f:
                f.write(data)
            os.replace(os.path.join(QUEUE, "." + name), os.path.join(QUEUE, name))
        earliest = datetime.now(TZ) + timedelta(seconds=MIN_WAIT)
        self.reply(201, f"In the queue. Not before {next_round(earliest).strftime('%a %d %b, %H:%M')}. " + self.summary())


if __name__ == "__main__":
    migrate.run(DATA, PUBLIC, log)
    os.makedirs(QUEUE, exist_ok=True)
    os.makedirs(PHOTOS, exist_ok=True)
    if not os.path.exists(INDEX):
        save(INDEX, [])
    log("photodiary started; round at", PUBLISH_AT, "| upload", "on" if TOKEN else "OFF", "| crate", DISCOGS_USER or "OFF")
    threading.Thread(target=clock, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), Upload).serve_forever()
