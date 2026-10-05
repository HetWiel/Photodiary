# One-time migration of data written by the old Dutch-named version of this server.
#
# Renames folders and files and translates the JSON keys in place, so the queue,
# the history of played records and every published day survive the switch.
# Runs on every start and does nothing once the data is in the new format.
# Safe to delete once the server has started once with this version.

import json
import os

PHOTO_KEYS = {"breed": "width", "hoog": "height", "sluiter": "shutter", "tijd": "time", "klein": "small"}
RECORD_KEYS = {"artiest": "artist", "titel": "title", "jaar": "year", "formaat": "format", "stijl": "style", "geluid": "sound"}


def _load(path):
    with open(path) as f:
        return json.load(f)


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _rename(d: dict, keys: dict) -> dict:
    return {keys.get(k, k): v for k, v in d.items()}


def _record(r):
    if not r:
        return r
    r = _rename(r, RECORD_KEYS)
    if isinstance(r.get("sound"), dict) and "fragment" in r["sound"]:
        r["sound"] = {"preview": r["sound"]["fragment"]}
    return r


def _photo(p):
    if not p:
        return p
    p = _rename(p, PHOTO_KEYS)
    for k in ("src", "small"):
        if isinstance(p.get(k), str):
            p[k] = p[k].replace("foto/", "photos/", 1).replace("-klein.webp", "-small.webp")
    return p


def run(data: str, public: str, log) -> None:
    # private: the queue, the played history and the cached collection
    old_queue, queue = os.path.join(data, "wachtrij"), os.path.join(data, "queue")
    if os.path.isdir(old_queue):
        os.makedirs(queue, exist_ok=True)
        for name in os.listdir(old_queue):
            os.replace(os.path.join(old_queue, name), os.path.join(queue, name))
        os.rmdir(old_queue)
        log("migrate: queue moved")

    old_state = os.path.join(data, "staat.json")
    if os.path.exists(old_state):
        _save(os.path.join(data, "state.json"), {"played": _load(old_state).get("gedraaid", [])})
        os.remove(old_state)
        log("migrate: state converted")

    old_crate = os.path.join(data, "krat.json")
    if os.path.exists(old_crate):
        mtime = os.path.getmtime(old_crate)
        new_crate = os.path.join(data, "crate.json")
        _save(new_crate, [_record(r) for r in _load(old_crate)])
        os.utime(new_crate, (mtime, mtime))  # keep the weekly refresh schedule
        os.remove(old_crate)
        log("migrate: crate converted")

    # public: the developed photos and index.json
    old_photos, photos = os.path.join(public, "foto"), os.path.join(public, "photos")
    if os.path.isdir(old_photos):
        os.makedirs(photos, exist_ok=True)
        for name in os.listdir(old_photos):
            os.replace(os.path.join(old_photos, name), os.path.join(photos, name.replace("-klein.webp", "-small.webp")))
        os.rmdir(old_photos)
        log("migrate: photos moved")

    index = os.path.join(public, "index.json")
    if os.path.exists(index):
        days = _load(index)
        if any("datum" in d for d in days):
            _save(index, [
                {"date": d.get("datum", d.get("date")),
                 "photo": _photo(d.get("foto", d.get("photo"))),
                 "record": _record(d.get("plaat", d.get("record")))}
                for d in days
            ])
            log(f"migrate: index converted ({len(days)} days)")
