# The crate: the record collection on Discogs.
#
# Fetches the collection at most once a week (the API is free but rate-limited)
# and picks a record each day that hasn't been played yet. Once everything has had
# its turn, it starts over. Cover images are deliberately not used: only the record's details.
#
# Needs: DISCOGS_USER (username). The collection must be public,
# or set DISCOGS_TOKEN (Discogs → Settings → Developers → Generate token).

import json
import os
import random
import re
import time
import urllib.parse
import urllib.request

API = "https://api.discogs.com"
AGENT = "hetwiel-photodiary/1.0 +https://hetwiel.dev"
WEEK = 7 * 24 * 3600


def _get(url: str, token: str | None) -> dict:
    headers = {"User-Agent": AGENT, "Accept": "application/vnd.discogs.v2.discogs+json"}
    if token:
        headers["Authorization"] = f"Discogs token={token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.load(r)


def _name(s: str) -> str:
    return re.sub(r"\s*\(\d+\)$", "", s or "").strip()  # Discogs numbers identical names: "Skream (2)"


def _record(item: dict) -> dict:
    b = item.get("basic_information", {})
    artists = ""
    entries = b.get("artists", [])
    for i, a in enumerate(entries):
        artists += _name(a.get("anv") or a.get("name", ""))
        if i < len(entries) - 1:
            join = (a.get("join") or ",").strip()
            artists += ", " if join == "," else f" {join} "
    artists = artists.strip() or "Unknown artist"
    labels = b.get("labels") or [{}]
    fmt = ""
    for f in b.get("formats", [])[:1]:
        parts = [d for d in f.get("descriptions", []) if d]
        fmt = ", ".join(parts) or f.get("name", "")
    return {
        "id": b.get("id") or item.get("id"),
        "artist": artists,
        "title": b.get("title", ""),
        "label": _name(labels[0].get("name", "")),
        "catno": (labels[0].get("catno") or "").replace("none", "").strip(),
        "year": b.get("year") or None,
        "format": fmt,
        "style": ", ".join((b.get("styles") or b.get("genres") or [])[:2]),
    }


def collection(folder: str, user: str, token: str | None) -> list[dict]:
    path = os.path.join(folder, "crate.json")
    old = None
    if os.path.exists(path):
        with open(path) as f:
            old = json.load(f)
        if time.time() - os.path.getmtime(path) < WEEK:
            return old
    try:
        records, page, pages = [], 1, 1
        while page <= pages:
            q = urllib.parse.urlencode({"per_page": 100, "page": page, "sort": "added"})
            data = _get(f"{API}/users/{urllib.parse.quote(user)}/collection/folders/0/releases?{q}", token)
            records += [_record(i) for i in data.get("releases", [])]
            pages = data.get("pagination", {}).get("pages", 1)
            page += 1
            time.sleep(1.2)  # well under the API's rate limit
    except Exception as e:
        print("crate: Discogs unreachable:", e, flush=True)
        return old or []
    if records:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(records, f)
        os.replace(tmp, path)
        print(f"crate: fetched {len(records)} records", flush=True)
    return records or old or []


def pick(records: list[dict], played: list) -> tuple[dict | None, list]:
    if not records:
        return None, played
    left = [r for r in records if r["id"] not in set(played)]
    if not left:  # everything has been played: the crate goes round again
        played, left = [], records
    r = random.choice(left)
    return r, played + [r["id"]]


# ── Sound: a snippet of the record ───────────────────────────────────
#
# First a 30-second preview from the iTunes search API (a fixed link to Apple,
# nothing is stored here). Not found? Then the first YouTube video listed on Discogs
# for the release; the site plays it visibly, in place of the photograph.

def _bare(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _similar(a: str, b: str) -> bool:
    a, b = _bare(a), _bare(b)
    return bool(a and b) and (a in b or b in a)


def _itunes(artist: str, titles: list[str]) -> str | None:
    for title in titles:
        q = urllib.parse.urlencode({"term": f"{artist} {title}", "entity": "song", "limit": 10})
        try:
            data = _get(f"https://itunes.apple.com/search?{q}", None)
        except Exception as e:
            print("crate: iTunes unreachable:", e, flush=True)
            return None
        for r in data.get("results", []):
            if r.get("previewUrl") and _similar(artist, r.get("artistName", "")) and _similar(title, r.get("trackName", "")):
                return r["previewUrl"]
        time.sleep(.5)
    return None


def sound(record: dict, token: str | None) -> dict:
    """{"preview": url} or {"video": youtube-id} or {} if there is nothing."""
    release = {}
    try:
        release = _get(f"{API}/releases/{record['id']}", token)
    except Exception as e:
        print("crate: could not fetch release:", e, flush=True)
    tracks = [t.get("title", "") for t in release.get("tracklist", []) if t.get("type_", "track") == "track"]
    # titles to search for: each track, then the release title (and the parts of "A / B")
    titles = tracks[:4] + [record["title"]] + [d.strip() for d in record["title"].split("/")]
    titles = list(dict.fromkeys(t for t in titles if t))
    artist = record["artist"].split(",")[0].split(" & ")[0]
    url = _itunes(artist, titles)
    if url:
        return {"preview": url}
    for v in release.get("videos", []):
        m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", v.get("uri", ""))
        if m:
            return {"video": m.group(1)}
    return {}
