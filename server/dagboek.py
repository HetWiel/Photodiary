# Het dagboek van hetwiel.dev.
#
# Twee dingen in één klein programma:
#
# 1. Een loket (poort 8080, via Caddy op upload.hetwiel.dev) waar de telefoon foto's heen stuurt.
#      POST /foto     de foto zelf als body, met "Authorization: Bearer <UPLOAD_TOKEN>"
#      POST /terug    haalt de laatst gestuurde foto weer uit de wachtrij
#      GET  /status   hoeveel foto's er wachten en wanneer de volgende verschijnt
#    Een foto wordt meteen gekeurd (donker genoeg? geen gezicht?). Afgekeurd = direct weg.
#
# 2. Een dagelijkse ronde (PUBLICEER_OM, Nederlandse tijd). Die pakt de oudste foto die
#    minstens WACHTTIJD_UUR in de wachtrij staat, keurt hem nog eens, ontwikkelt hem
#    en kiest een plaat uit de krat. Samen worden ze één regel in /publiek/index.json.
#    Het origineel wordt daarna gewist. Geen foto die dag? Dan alleen de plaat.
#
# Caddy serveert /publiek als dagboek.hetwiel.dev/data/. De site (site/) leest daar index.json.

import hmac
import json
import os
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import beeld
import krat

TZ = ZoneInfo(os.environ.get("TZ", "Europe/Amsterdam"))
TOKEN = os.environ.get("UPLOAD_TOKEN", "")
DISCOGS_USER = os.environ.get("DISCOGS_USER", "")
DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN") or None
PUBLICEER_OM = os.environ.get("PUBLICEER_OM", "00:10")
WACHTTIJD = float(os.environ.get("WACHTTIJD_UUR", "24")) * 3600
MAX_BYTES = 40 * 1024 * 1024

DATA = os.environ.get("DATA", "/data")
PUBLIEK = os.environ.get("PUBLIEK", "/publiek")
WACHTRIJ = os.path.join(DATA, "wachtrij")
STAAT = os.path.join(DATA, "staat.json")
INDEX = os.path.join(PUBLIEK, "index.json")
FOTO = os.path.join(PUBLIEK, "foto")

slot = threading.Lock()


def log(*a):
    print(datetime.now(TZ).strftime("%Y-%m-%d %H:%M"), *a, flush=True)


def lees(pad, standaard):
    try:
        with open(pad) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return standaard


def schrijf(pad, data):
    tmp = pad + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, pad)


def wachtend():
    """Foto's in de wachtrij, oudste eerst. De naam begint met het moment van insturen."""
    return sorted(n for n in os.listdir(WACHTRIJ) if not n.startswith("."))


def ingestuurd(naam):
    return datetime.strptime(naam[:15], "%Y%m%dT%H%M%S").replace(tzinfo=TZ).timestamp()


def volgende_ronde(na: datetime) -> datetime:
    u, m = (int(x) for x in PUBLICEER_OM.split(":"))
    t = na.replace(hour=u, minute=m, second=0, microsecond=0)
    return t if t > na else t + timedelta(days=1)


# ── De dagelijkse ronde ──────────────────────────────────────────────

def ronde(dag: date):
    with slot:
        index = lees(INDEX, [])
        if any(r["datum"] == dag.isoformat() for r in index):
            return
        staat = lees(STAAT, {"gedraaid": []})

        foto = None
        for naam in wachtend():
            if time.time() - ingestuurd(naam) < WACHTTIJD:
                break
            pad = os.path.join(WACHTRIJ, naam)
            try:
                with open(pad, "rb") as f:
                    img = beeld.open_foto(f.read())
                beeld.keur(img)
                groot, klein = beeld.ontwikkel(img, zaad=dag.toordinal())
                info = beeld.gegevens(img)
            except beeld.Afgekeurd as e:
                log("afgekeurd bij publiceren:", naam, e)
                os.remove(pad)
                continue
            os.makedirs(FOTO, exist_ok=True)
            d = dag.isoformat()
            groot.save(os.path.join(FOTO, f"{d}.webp"), "WEBP", quality=80, method=6)
            klein.save(os.path.join(FOTO, f"{d}-klein.webp"), "WEBP", quality=78, method=6)
            foto = {"src": f"foto/{d}.webp", "klein": f"foto/{d}-klein.webp",
                    "breed": groot.width, "hoog": groot.height, **info}
            os.remove(pad)  # het origineel, met alle metadata, verdwijnt
            break

        plaat = None
        if DISCOGS_USER:
            platen = krat.collectie(DATA, DISCOGS_USER, DISCOGS_TOKEN)
            plaat, staat["gedraaid"] = krat.kies(platen, staat["gedraaid"])
            if plaat:
                plaat = {**plaat, "link": f"https://www.discogs.com/release/{plaat['id']}",
                         "geluid": krat.geluid(plaat, DISCOGS_TOKEN)}

        if not foto and not plaat:
            log("niets te publiceren voor", dag)
            return
        index.insert(0, {"datum": dag.isoformat(), "foto": foto, "plaat": plaat})
        index.sort(key=lambda r: r["datum"], reverse=True)
        schrijf(INDEX, index)
        schrijf(STAAT, staat)
        log("gepubliceerd:", dag, "foto" if foto else "geen foto", "+", plaat["artiest"] + " – " + plaat["titel"] if plaat else "geen plaat")


def geluid_aanvullen():
    """Dagen van vóór het geluid: geef de plaat van vandaag alsnog een fragment."""
    with slot:
        index = lees(INDEX, [])
        if index and index[0].get("plaat") and "geluid" not in index[0]["plaat"]:
            index[0]["plaat"]["geluid"] = krat.geluid(index[0]["plaat"], DISCOGS_TOKEN)
            schrijf(INDEX, index)
            log("geluid aangevuld:", index[0]["plaat"]["geluid"] or "niets gevonden")


def klok():
    # Bij het opstarten: is de ronde van vandaag al geweest? Zo niet, en is het tijdstip voorbij, dan nu.
    nu = datetime.now(TZ)
    u, m = (int(x) for x in PUBLICEER_OM.split(":"))
    if nu.replace(hour=u, minute=m, second=0, microsecond=0) <= nu:
        try:
            ronde(nu.date())
        except Exception as e:
            log("fout in ronde:", repr(e))
    try:
        geluid_aanvullen()
    except Exception as e:
        log("fout bij geluid:", repr(e))
    while True:
        t = volgende_ronde(datetime.now(TZ))
        while (wacht := (t - datetime.now(TZ)).total_seconds()) > 0:
            time.sleep(min(wacht, 300))
        try:
            ronde(t.date())
        except Exception as e:
            log("fout in ronde:", repr(e))


# ── Het loket ────────────────────────────────────────────────────────

class Loket(BaseHTTPRequestHandler):
    server_version = "dagboek"
    sys_version = ""

    def log_message(self, fmt, *args):  # geen IP-adressen in de logs
        pass

    def antwoord(self, code, tekst):
        body = (tekst + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def toegang(self):
        if not TOKEN:
            self.antwoord(503, "Upload is not set up (no UPLOAD_TOKEN).")
            return False
        kop = self.headers.get("Authorization", "")
        if not hmac.compare_digest(kop.encode(), f"Bearer {TOKEN}".encode()):
            time.sleep(1)
            self.antwoord(401, "No.")
            return False
        return True

    def lees_body(self):
        """De body, met of zonder Content-Length (sommige apps sturen 'chunked')."""
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            delen, totaal = [], 0
            while True:
                grootte = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if grootte == 0:
                    self.rfile.readline()
                    break
                totaal += grootte
                if totaal > MAX_BYTES:
                    return None
                delen.append(self.rfile.read(grootte))
                self.rfile.readline()
            return b"".join(delen)
        lengte = int(self.headers.get("Content-Length") or 0)
        if not 0 < lengte <= MAX_BYTES:
            return None
        return self.rfile.read(lengte)

    def stand(self):
        n = len(wachtend())
        volgende = volgende_ronde(datetime.now(TZ)).strftime("%a %d %b, %H:%M")
        return f"{n} waiting. Next round: {volgende}."

    def do_GET(self):
        if self.path == "/gezond":
            return self.antwoord(200, "ok")
        if self.path == "/status":
            if self.toegang():
                self.antwoord(200, self.stand())
            return
        self.antwoord(404, "Not here.")

    def do_POST(self):
        if self.path not in ("/foto", "/terug"):
            return self.antwoord(404, "Not here.")
        if not self.toegang():
            return
        if self.path == "/terug":
            with slot:
                rij = wachtend()
                if not rij:
                    return self.antwoord(200, "Queue is empty.")
                os.remove(os.path.join(WACHTRIJ, rij[-1]))
            return self.antwoord(200, "Last photo removed. " + self.stand())

        data = self.lees_body()
        if not data:
            return self.antwoord(413, "Too large or empty.")
        try:
            img = beeld.open_foto(data)
            beeld.keur(img)
        except beeld.Afgekeurd as e:
            return self.antwoord(422, f"Not accepted: {e}. Nothing was kept.")
        naam = datetime.now(TZ).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4)
        with slot:
            with open(os.path.join(WACHTRIJ, "." + naam), "wb") as f:
                f.write(data)
            os.replace(os.path.join(WACHTRIJ, "." + naam), os.path.join(WACHTRIJ, naam))
        vroegst = datetime.now(TZ) + timedelta(seconds=WACHTTIJD)
        self.antwoord(201, f"In the queue. Not before {volgende_ronde(vroegst).strftime('%a %d %b, %H:%M')}. " + self.stand())


if __name__ == "__main__":
    os.makedirs(WACHTRIJ, exist_ok=True)
    os.makedirs(FOTO, exist_ok=True)
    if not os.path.exists(INDEX):
        schrijf(INDEX, [])
    log("dagboek start; ronde om", PUBLICEER_OM, "| upload", "aan" if TOKEN else "UIT", "| krat", DISCOGS_USER or "UIT")
    threading.Thread(target=klok, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), Loket).serve_forever()
