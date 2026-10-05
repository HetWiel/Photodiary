# De krat: de platencollectie op Discogs.
#
# Haalt de collectie hooguit één keer per week op (de API is gratis maar heeft een limiet)
# en kiest elke dag een plaat die nog niet gedraaid is. Is alles geweest, dan begint het opnieuw.
# Hoesafbeeldingen worden bewust niet gebruikt: alleen de gegevens van de plaat.
#
# Nodig: DISCOGS_USER (gebruikersnaam). De collectie moet openbaar zijn,
# of zet DISCOGS_TOKEN (Discogs → Settings → Developers → Generate token).

import json
import os
import random
import re
import time
import urllib.parse
import urllib.request

API = "https://api.discogs.com"
AGENT = "hetwiel-dagboek/1.0 +https://hetwiel.dev"
WEEK = 7 * 24 * 3600


def _haal(url: str, token: str | None) -> dict:
    kop = {"User-Agent": AGENT, "Accept": "application/vnd.discogs.v2.discogs+json"}
    if token:
        kop["Authorization"] = f"Discogs token={token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=kop), timeout=30) as r:
        return json.load(r)


def _naam(s: str) -> str:
    return re.sub(r"\s*\(\d+\)$", "", s or "").strip()  # Discogs nummert gelijke namen: "Skream (2)"


def _plaat(item: dict) -> dict:
    b = item.get("basic_information", {})
    artiesten = ""
    lijst = b.get("artists", [])
    for i, a in enumerate(lijst):
        artiesten += _naam(a.get("anv") or a.get("name", ""))
        if i < len(lijst) - 1:
            join = (a.get("join") or ",").strip()
            artiesten += ", " if join == "," else f" {join} "
    artiesten = artiesten.strip() or "Unknown artist"
    labels = b.get("labels") or [{}]
    formaat = ""
    for f in b.get("formats", [])[:1]:
        delen = [d for d in f.get("descriptions", []) if d]
        formaat = ", ".join(delen) or f.get("name", "")
    return {
        "id": b.get("id") or item.get("id"),
        "artiest": artiesten,
        "titel": b.get("title", ""),
        "label": _naam(labels[0].get("name", "")),
        "catno": (labels[0].get("catno") or "").replace("none", "").strip(),
        "jaar": b.get("year") or None,
        "formaat": formaat,
        "stijl": ", ".join((b.get("styles") or b.get("genres") or [])[:2]),
    }


def collectie(map_: str, gebruiker: str, token: str | None) -> list[dict]:
    pad = os.path.join(map_, "krat.json")
    oud = None
    if os.path.exists(pad):
        with open(pad) as f:
            oud = json.load(f)
        if time.time() - os.path.getmtime(pad) < WEEK:
            return oud
    try:
        platen, pagina, paginas = [], 1, 1
        while pagina <= paginas:
            q = urllib.parse.urlencode({"per_page": 100, "page": pagina, "sort": "added"})
            data = _haal(f"{API}/users/{urllib.parse.quote(gebruiker)}/collection/folders/0/releases?{q}", token)
            platen += [_plaat(i) for i in data.get("releases", [])]
            paginas = data.get("pagination", {}).get("pages", 1)
            pagina += 1
            time.sleep(1.2)  # ruim onder de limiet van de API
    except Exception as e:
        print("krat: Discogs niet bereikbaar:", e, flush=True)
        return oud or []
    if platen:
        tmp = pad + ".tmp"
        with open(tmp, "w") as f:
            json.dump(platen, f)
        os.replace(tmp, pad)
        print(f"krat: {len(platen)} platen opgehaald", flush=True)
    return platen or oud or []


def kies(platen: list[dict], gedraaid: list) -> tuple[dict | None, list]:
    if not platen:
        return None, gedraaid
    over = [p for p in platen if p["id"] not in set(gedraaid)]
    if not over:  # alles is geweest: de krat gaat opnieuw rond
        gedraaid, over = [], platen
    p = random.choice(over)
    return p, gedraaid + [p["id"]]


# ── Geluid: een fragment van de plaat ────────────────────────────────
#
# Eerst een voorproef van 30 seconden uit de iTunes-zoekdienst (een vaste link naar Apple,
# niets wordt hier opgeslagen). Niet gevonden? Dan de eerste YouTube-video die op Discogs
# bij de release staat; de site speelt die zichtbaar af, op de plek van de foto.

def _kaal(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _lijkt(a: str, b: str) -> bool:
    a, b = _kaal(a), _kaal(b)
    return bool(a and b) and (a in b or b in a)


def _itunes(artiest: str, titels: list[str]) -> str | None:
    for titel in titels:
        q = urllib.parse.urlencode({"term": f"{artiest} {titel}", "entity": "song", "limit": 10})
        try:
            data = _haal(f"https://itunes.apple.com/search?{q}", None)
        except Exception as e:
            print("krat: iTunes niet bereikbaar:", e, flush=True)
            return None
        for r in data.get("results", []):
            if r.get("previewUrl") and _lijkt(artiest, r.get("artistName", "")) and _lijkt(titel, r.get("trackName", "")):
                return r["previewUrl"]
        time.sleep(.5)
    return None


def geluid(plaat: dict, token: str | None) -> dict:
    """{"fragment": url} of {"video": youtube-id} of {} als er niets is."""
    release = {}
    try:
        release = _haal(f"{API}/releases/{plaat['id']}", token)
    except Exception as e:
        print("krat: release niet op te halen:", e, flush=True)
    sporen = [t.get("title", "") for t in release.get("tracklist", []) if t.get("type_", "track") == "track"]
    # titels om op te zoeken: elk spoor, dan de releasetitel (en de delen van "A / B")
    titels = sporen[:4] + [plaat["titel"]] + [d.strip() for d in plaat["titel"].split("/")]
    titels = list(dict.fromkeys(t for t in titels if t))
    artiest = plaat["artiest"].split(",")[0].split(" & ")[0]
    url = _itunes(artiest, titels)
    if url:
        return {"fragment": url}
    for v in release.get("videos", []):
        m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", v.get("uri", ""))
        if m:
            return {"video": m.group(1)}
    return {}
