# De server van het dagboek

Elke nacht één foto en één plaat op dagboek.hetwiel.dev (*Today* op `/`, alles op `/archive/`).

## Hoe het werkt

1. **Insturen.** Deel een foto vanaf de telefoon naar `https://upload.hetwiel.dev/foto`.
   Hij wordt meteen gekeurd: een gezicht gevonden (YuNet, ook in een opgehelderde kopie) → geweigerd.
   Lichte foto's mogen: bij het ontwikkelen worden ze donkerder belicht (zie `DOEL_HELDERHEID`).
   Geweigerd = direct weg, er wordt niets bewaard. De telefoon krijgt de reden te zien.
2. **Wachten.** Een goedgekeurde foto staat minstens `WACHTTIJD_UUR` (24) in de wachtrij.
   Spijt? `POST /terug` haalt de laatst ingestuurde weer weg.
3. **De ronde** (`PUBLICEER_OM`, 00:10 Nederlandse tijd). De oudste foto die lang genoeg wacht
   wordt nog een keer gekeurd en ontwikkeld: bijgesneden tot 9:5 (het formaat van de wieltekening),
   zwart-wit, diepe schaduwen, lichte foto's donkerder belicht, het vignet van de wieltekening, korrel. Het nieuwe bestand heeft geen metadata (geen GPS, geen toestel);
   het origineel wordt gewist. Alleen sluitertijd, ISO en het tijdstip gaan mee.
4. **De krat.** Een willekeurige plaat uit de Discogs-collectie die nog niet geweest is.
   Geen hoes, alleen de gegevens, met een link naar de release.
   Plus een fragment: een voorproef van 30 s via iTunes, anders de YouTube-video die op Discogs
   bij de release staat. Klik op de foto op *Today* om te luisteren.
5. Alles komt in `index.json`, die Caddy serveert op `dagboek.hetwiel.dev/data/`.

Geen foto die dag? Dan alleen de plaat, met een lege zwarte plaat ernaast.

**Let op:** de gezichtsherkenning is een vangnet, geen garantie. Iemand van achteren,
of een kind half in beeld, wordt niet altijd herkend. De echte filter is dat alleen
foto's binnenkomen die je zelf bewust deelt.

## Instellen (eenmalig, op de server)

```bash
cd /opt/hetwiel && mkdir -p env
cat > env/dagboek.env <<EOT
UPLOAD_TOKEN=$(openssl rand -hex 24)
DISCOGS_USER=<je Discogs-gebruikersnaam>
# DISCOGS_TOKEN=<alleen nodig als je collectie niet openbaar is>
EOT
chmod 600 env/dagboek.env
cat env/dagboek.env          # het token heb je zo nodig op de telefoon
docker compose up -d dagboek
docker logs dagboek          # "upload aan | krat <naam>"
```

Optioneel in hetzelfde bestand: `PUBLICEER_OM=00:10`, `WACHTTIJD_UUR=24`, `DOEL_HELDERHEID=0.3` (lager = donkerder platen).

## De telefoon (Android, app *HTTP Shortcuts*)

Shortcut **Dagboek**:
- Method `POST`, URL `https://upload.hetwiel.dev/foto`
- Request Body: **File** → *File from share* (of: *Image*)
- Header `Authorization` = `Bearer <UPLOAD_TOKEN>`
- Trigger & Execution Settings: **Allow receiving shared files** aan
- Response Handling: toon het antwoord als melding

Daarna staat *Dagboek* in het deelmenu van de galerij.

Shortcut **Dagboek terug** (zelfde header): `POST https://upload.hetwiel.dev/terug`.
Shortcut **Dagboek status** (zelfde header): `GET https://upload.hetwiel.dev/status`.

## Bestanden

```
dagboek.py   het loket en de dagelijkse ronde
beeld.py     keuren en ontwikkelen
krat.py      Discogs
face_detection_yunet_2023mar.onnx   gezichtsmodel (OpenCV Zoo, MIT-licentie)
```

Data staat in Docker-volumes: `dagboek_data` (wachtrij, krat, wat al gedraaid is: privé)
en `dagboek_publiek` (de ontwikkelde foto's en `index.json`: online).
