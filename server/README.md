# The Photodiary server

One photograph and one record every night on photodiary.hetwiel.dev (*Today* at `/`, everything at `/archive/`).

## How it works

1. **Sending.** Share a photo from the phone to `https://upload.hetwiel.dev/photo`.
   It is checked straight away: a face found (YuNet, also on a brightened copy) → rejected.
   Bright photos are fine: they are exposed darker when developed (see `TARGET_BRIGHTNESS`).
   Rejected = deleted immediately, nothing is kept. The phone shows the reason.
2. **Waiting.** An accepted photo stays in the queue for at least `MIN_WAIT_HOURS` (24).
   Changed your mind? `POST /undo` removes the most recently sent one.
3. **The round** (`PUBLISH_AT`, 00:10 Amsterdam time). The oldest photo that has waited long enough
   is checked once more and developed: cropped to 9:5 (the format of the wheel drawing),
   black and white, deep shadows, bright photos exposed darker, the vignette of the wheel drawing, grain.
   The new file has no metadata (no GPS, no camera); the original is deleted.
   Only shutter speed, ISO and the time of day are kept.
4. **The crate.** A random record from the Discogs collection that hasn't been played yet.
   No cover, just the details, with a link to the release.
   Plus a snippet: a 30-second preview from iTunes, otherwise the YouTube video listed on Discogs
   for the release. Click the photo on *Today* to listen.
5. Everything goes into `index.json`, which Caddy serves at `photodiary.hetwiel.dev/data/`.

No photo that day? Then just the record, with an empty black plate next to it.

**Note:** face detection is a safety net, not a guarantee. Someone seen from behind,
or a child half in frame, isn't always detected. The real filter is that only
photos you deliberately share come in.

## Setup (once, on the server)

```bash
cd /opt/hetwiel && mkdir -p env
cat > env/photodiary.env <<EOT
UPLOAD_TOKEN=$(openssl rand -hex 24)
DISCOGS_USER=<your Discogs username>
# DISCOGS_TOKEN=<only needed if your collection isn't public>
EOT
chmod 600 env/photodiary.env
cat env/photodiary.env          # you'll need the token on the phone
docker compose up -d photodiary
docker logs photodiary          # "upload on | crate <name>"
```

Optional in the same file: `PUBLISH_AT=00:10`, `MIN_WAIT_HOURS=24`, `TARGET_BRIGHTNESS=0.3` (lower = darker plates).

## The phone (Android, *HTTP Shortcuts* app)

Shortcut **Photodiary**:
- Method `POST`, URL `https://upload.hetwiel.dev/photo`
- Request Body: **File** → *File from share* (or: *Image*)
- Header `Authorization` = `Bearer <UPLOAD_TOKEN>`
- Trigger & Execution Settings: **Allow receiving shared files** on
- Response Handling: show the response as a notification

*Photodiary* then appears in the gallery's share menu.

Shortcut **Photodiary undo** (same header): `POST https://upload.hetwiel.dev/undo`.
Shortcut **Photodiary status** (same header): `GET https://upload.hetwiel.dev/status`.

## Files

```
diary.py     the upload endpoint and the daily round
photo.py     checking and developing
crate.py     Discogs
migrate.py   one-time conversion of data from the old Dutch-named version (can go after one start)
face_detection_yunet_2023mar.onnx   face model (OpenCV Zoo, MIT licence)
```

Data lives in Docker volumes: `photodiary_data` (queue, crate, what has been played: private)
and `photodiary_public` (the developed photos and `index.json`: online).
