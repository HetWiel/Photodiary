# Photodiary

One photograph and one record every night, at **https://photodiary.hetwiel.dev**.
A script checks the photo (no faces), develops it in black and white in the format of the
wheel drawing on hetwiel.dev (9:5) and picks a record from the Discogs crate to go with it,
with a snippet to listen to.

```
site/     the website: Today (/) and Archive (/archive/). Plain HTML, no build step.
server/   the container: the upload endpoint for the phone (upload.hetwiel.dev) and the nightly round.
          How it works, setup and the phone: server/README.md
```

## How it goes live

This repo is part of the server setup in **HetWiel/hetwiel**. Its deploy workflow fetches this repo
on every push to hetwiel, every morning, or when started by hand (Actions → Deploy hetwiel →
Run workflow), and puts:

- `site/` in `sites/photodiary` → Caddy serves it on photodiary.hetwiel.dev;
- `server/` in `services/photodiary` → `docker compose` builds and starts the container.

A change here is live after the next deploy of hetwiel.

## Viewing locally

```bash
cd site && python3 -m http.server 8000
```

Without `data/index.json` the site shows "Nothing yet". Put a copy of the real one
(`https://photodiary.hetwiel.dev/data/index.json`) in `site/data/` to look at real data;
`site/data/` is in `.gitignore`.
