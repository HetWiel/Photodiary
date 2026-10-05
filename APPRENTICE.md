# The Apprentice: Photodiary

The machine built this work. This file is the other half: one card per material, so the
maker can learn what was built. The levels live in `apprentice.yml`; the rules of the loop
are in `CLAUDE.md` and the skill `.claude/skills/apprentice/`.

How a card is used in a teach-back:
1. The maker reads *What it is* and *Where it lives*, and opens the files.
2. The maker explains the material in his own words, without looking.
3. The machine asks the *Questions* and judges the answers: understood, half, or not yet.
4. Understood → level `understood`. Later, doing the *By hand* task → `by-hand`.

Ledger opened: 5 October 2026 (retroactive: everything below was built before the loop existed).

---

## http-endpoint · An upload endpoint

**What it is.** `diary.py` runs a small web server (Python's own `http.server`) on port 8080
with four routes: `POST /photo`, `POST /undo`, `GET /status`, `GET /health`. Caddy passes
`upload.hetwiel.dev` through to it.

**Where it lives.** `server/diary.py` (class `Upload`); the `upload.hetwiel.dev` block in the hetwiel `Caddyfile`.

**Why this way.** No framework needed for four routes; everything fits in one readable file.

**Questions.**
- What do the status codes 201, 401, 413 and 422 mean in this file?
- Why does `/health` not need a token?
- What does `read_body` do with a *chunked* upload, and why was that needed?

**By hand.** Call `/health` and `/status` yourself with `curl`, with and without the token.

---

## bearer-token · A secret token

**What it is.** Every request (except `/health`) needs the header `Authorization: Bearer <UPLOAD_TOKEN>`.
The token lives only in `env/photodiary.env` on the server and in the phone's shortcut.
It is compared with `hmac.compare_digest`, and a wrong token waits a second before answering.

**Where it lives.** `server/diary.py` (`authorised`), `server/README.md` (Setup).

**Why this way.** Simple and strong enough for one user; nothing to log in to.

**Questions.**
- Why `compare_digest` instead of `==`?
- What is the `time.sleep(1)` for?
- Why can't someone read the token while it travels from the phone?

**By hand.** Generate a new token (`openssl rand -hex 24`), put it on the server and the phone, and test.

---

## phone-share · Sharing from the phone

**What it is.** The Android app *HTTP Shortcuts* adds *Photodiary* to the gallery's share
menu: it POSTs the shared file with the token header and shows the server's answer as a notification.

**Where it lives.** `server/README.md` (The phone).

**Why this way.** Sharing a photo is something the hand already knows; no app to build.

**Questions.**
- What does the phone actually send, in terms of method, URL, header and body?
- Where does the text in the notification come from?
- What would you change to send from a laptop instead?

**By hand.** Build the *Photodiary status* shortcut yourself from the README.

---

## queue · A queue on disk

**What it is.** Accepted photos are written to `/data/queue`, named by date and time. The round takes
the oldest one that has waited at least `MIN_WAIT_HOURS`. `/undo` removes the newest. A photo is first
written under a hidden name and then renamed, so the round never sees half a file.

**Where it lives.** `server/diary.py` (`waiting`, `do_POST`, `publish`).

**Why this way.** A day of waiting gives room to change your mind; files are the simplest queue there is.

**Questions.**
- Why the 24-hour wait?
- Why write to `.name` first and then `os.replace`?
- What happens when you send five photos on one day?

**By hand.** Change `MIN_WAIT_HOURS` to 12 in `env/photodiary.env`, restart the container and check `/status`.

---

## threads · Two things at once

**What it is.** The program runs two threads: the web server, and `clock`, which sleeps until the next
round. They share the queue and `index.json`, so both take a `lock` before touching them.

**Where it lives.** `server/diary.py` (`lock`, `clock`, the last lines).

**Why this way.** One container, one program, no separate scheduler.

**Questions.**
- What could go wrong if `/undo` and the round ran at exactly the same moment without the lock?
- Why does `clock` sleep in steps of at most 300 seconds?
- What does `daemon=True` mean for the clock thread?

**By hand.** Read `clock()` and explain out loud what happens when the container starts at 09:00.

---

## time-zones · Clocks and time zones

**What it is.** `PUBLISH_AT` (00:10) is Amsterdam time, set with `ZoneInfo` and `TZ` in `docker-compose.yml`.
`next_round` works out the next moment that time comes around.

**Where it lives.** `server/diary.py` (`TZ`, `next_round`), the hetwiel `docker-compose.yml` (`TZ: Europe/Amsterdam`).

**Why this way.** Servers often run in UTC; a diary follows the maker's day.

**Questions.**
- What happens to the round on the night the clocks go back in October?
- Why does `next_round` add a day in some cases?
- Why is the round at 00:10 and not 00:00?

**By hand.** Change `PUBLISH_AT` to a time in five minutes, restart, and watch the log.

---

## face-detection · Face detection

**What it is.** YuNet, a small trained model (the `.onnx` file), runs through OpenCV. It looks at the
photo twice: as it is and brightened (CLAHE), because dark photos hide faces. One face anywhere → rejected.

**Where it lives.** `server/photo.py` (`_faces`, `check`), `server/face_detection_yunet_2023mar.onnx`.

**Why this way.** No faces of other people online, checked on arrival and again before publishing.

**Questions.**
- Why look twice, once brightened?
- What does the README say this check does *not* guarantee?
- What does the 0.6 in `FaceDetectorYN.create` probably control?

**By hand.** Send a photo with a face on purpose and read the phone's answer.

---

## image-processing · Developing a photo in code

**What it is.** `develop` turns the photo into numbers between 0 and 1 and works on them: crop to 9:5,
black and white, levels, an S-curve, darker exposure when too bright, the vignette and shadow of the wheel
drawing, grain seeded by the date. Then two WebP files, large and small.

**Where it lives.** `server/photo.py` (`_crop`, `develop`).

**Why this way.** Every plate looks like it belongs next to the wheel drawing, without editing by hand.

**Questions.**
- Why 9:5?
- Why is the grain seeded with the date (`seed=day.toordinal()`)?
- What does `TARGET_BRIGHTNESS` do, in words a photographer would use?

**By hand.** Make the grain stronger and develop one test photo locally.

---

## metadata · Photo metadata

**What it is.** A phone photo carries EXIF data: GPS position, camera, date. `details` keeps only
shutter speed, ISO and the time of day. The developed plate is a new image with no metadata at all,
and the original is deleted.

**Where it lives.** `server/photo.py` (`details`), `server/diary.py` (`os.remove(path)` in `publish`).

**Why this way.** A photo of your street must not reveal where your street is.

**Questions.**
- Which EXIF fields would have been dangerous to publish?
- Why does `_grey` call `exif_transpose` first?
- Is there any moment when the original with GPS is on the server? How long?

**By hand.** Look up the EXIF of a phone photo and of a published plate, and compare.

---

## external-apis · Other people's APIs

**What it is.** Discogs gives the record collection and per release the tracklist and videos; iTunes
Search gives a 30-second preview. The crate is cached, records already played are remembered.

**Where it lives.** `server/crate.py` (`collection`, `pick`, `sound`, `_itunes`).

**Why this way.** Public APIs, no keys needed for a public collection.

**Questions.**
- Why is there a `time.sleep(.5)` between iTunes searches?
- What happens when every record in the crate has been played?
- What does `_similar` protect against?

**By hand.** Search the iTunes API yourself in the browser for one of your records.

---

## dockerfile · Building a container

**What it is.** The `Dockerfile` starts from `python:3.12-slim`, installs the requirements, creates a
system user `photodiary` and runs as that user. The hetwiel deploy builds it on the server.

**Where it lives.** `server/Dockerfile`, `server/requirements.txt`.

**Why this way.** If something were ever broken into, it would not be `root`.

**Questions.**
- Why is `requirements.txt` copied before the code?
- Why are `/data` and `/public` created and given an owner in the image?
- What does `PYTHONUNBUFFERED=1` do for `docker logs`?

**By hand.** Build the image locally with `docker build` and start it without a token; read its first log line.

---

## migration · Moving data safely

**What it is.** When the project went from Dutch (*dagboek*) to English (*Photodiary*), `migrate.py`
renamed the fields in the stored data on start-up, and the hetwiel deploy copied the old volumes to new
ones, keeping the old ones as a backup.

**Where it lives.** `server/migrate.py`, the hetwiel workflow step *Move Photodiary data from the old Dutch names*.

**Why this way.** Renaming is easy; renaming without losing a night is the work.

**Questions.**
- Why copy the volumes instead of renaming them?
- Why is it safe to run `migrate.run` on every start?
- When can `migrate.py` be deleted?

**By hand.** Remove the one-time migration step from the hetwiel workflow, now that it has run.

---

## Teach-back log

Each session: date, materials covered, result. Newest at the top.

<!-- 2026-10-05 · ledger opened; all materials at `seen` -->
