# Dagboek

Elke nacht één foto en één plaat, op **https://dagboek.hetwiel.dev**.
Een script keurt de foto (geen gezichten), ontwikkelt hem in zwart-wit in het formaat van de
wieltekening op hetwiel.dev (9:5) en kiest er een plaat uit de Discogs-krat bij, met een fragment
om te luisteren.

```
site/     de website: Today (/) en Archive (/archive/). Gewone HTML, geen bouwstap.
server/   de container: het loket voor de telefoon (upload.hetwiel.dev) en de nachtelijke ronde.
          Uitleg, instellen en de telefoon: server/README.md
```

## Hoe het live komt

Deze repo draait mee in de server-setup van **HetWiel/hetwiel**. Die bouwrobot haalt deze repo op
bij elke push naar hetwiel, elke ochtend, of als je hem met de hand start (Actions → Deploy hetwiel →
Run workflow), en zet:

- `site/` in `sites/dagboek` → Caddy serveert het op dagboek.hetwiel.dev;
- `server/` in `diensten/dagboek` → `docker compose` bouwt en start de container.

Een wijziging hier staat dus live na de volgende deploy van hetwiel.

## Lokaal kijken

```bash
cd site && python3 -m http.server 8000
```

Zonder `data/index.json` toont de site "Nothing yet". Zet er een kopie van de echte neer
(`https://dagboek.hetwiel.dev/data/index.json`) in `site/data/` om met echte gegevens te kijken;
`site/data/` staat in `.gitignore`.
