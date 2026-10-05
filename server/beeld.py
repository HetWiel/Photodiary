# Het beeld: keuren en ontwikkelen.
#
# keur()      staat er een gezicht op? Dan niet publiceren.
# ontwikkel() maakt er een plaat van in de stijl van de site: zwart-wit, diepe schaduwen,
#             een vignet zoals bij de tekening van het wiel, en korrel. Lichte foto's worden
#             eerst donkerder "belicht", zodat elke plaat in hetzelfde donker eindigt.
#             Het resultaat is een nieuw bestand zonder metadata: geen GPS, geen toestel.

import io
import os
from fractions import Fraction

import cv2
import numpy as np
from PIL import Image, ImageOps

try:  # foto's van sommige Android-telefoons zijn HEIC
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_detection_yunet_2023mar.onnx")
# hoe licht een plaat gemiddeld mag zijn vóór vignet en korrel; lichtere foto's worden donkerder gemaakt
DOEL_HELDERHEID = float(os.environ.get("DOEL_HELDERHEID", "0.3"))

DONKER = np.array([0x0C, 0x0B, 0x0A], np.float32) / 255   # de zwarte plaat van de site
LICHT = np.array([0xDC, 0xD5, 0xC7], np.float32) / 255    # de lijnkleur van de tekening

Image.MAX_IMAGE_PIXELS = 80_000_000


class Afgekeurd(Exception):
    """De foto gaat niet online. De reden is kort en leesbaar, voor de melding op de telefoon."""


def open_foto(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise Afgekeurd("not an image")
    return img


def gegevens(img: Image.Image) -> dict:
    """Sluitertijd, ISO en het tijdstip (zonder datum). Meer niet."""
    uit = {}
    try:
        exif = img.getexif().get_ifd(0x8769)
    except Exception:
        return uit
    t = exif.get(33434)  # ExposureTime
    if t:
        t = float(t)
        if t > 0:
            uit["sluiter"] = f"{t:g} s" if t >= 1 else f"1/{round(1 / t)} s"
    iso = exif.get(34855)  # ISOSpeedRatings
    if isinstance(iso, (tuple, list)):
        iso = iso[0] if iso else None
    if iso:
        uit["iso"] = int(iso)
    moment = exif.get(36867) or exif.get(36868)  # DateTimeOriginal / Digitized: "2026:10:04 23:52:10"
    if isinstance(moment, str) and len(moment) >= 16:
        uit["tijd"] = moment[11:16]
    return uit


def _grijs(img: Image.Image) -> Image.Image:
    return ImageOps.exif_transpose(img).convert("L")


_detector = None


def _gezichten(img: Image.Image) -> int:
    """Telt gezichten met YuNet. Kijkt twee keer: zoals de foto is, en opgehelderd
    (in donkere foto's ziet het model anders te weinig)."""
    global _detector
    rgb = np.asarray(ImageOps.exif_transpose(img).convert("RGB"))
    h, w = rgb.shape[:2]
    schaal = min(1.0, 1280 / max(h, w))
    if schaal < 1:
        rgb = cv2.resize(rgb, (round(w * schaal), round(h * schaal)), interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    licht = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(MODEL, "", (320, 320), 0.6, 0.3, 5000)
    totaal = 0
    for beeld in (bgr, licht):
        _detector.setInputSize((beeld.shape[1], beeld.shape[0]))
        _, gevonden = _detector.detect(beeld)
        totaal = max(totaal, 0 if gevonden is None else len(gevonden))
    return totaal


def keur(img: Image.Image) -> None:
    if _gezichten(img):
        raise Afgekeurd("face detected")


FORMAAT = Fraction(9, 5)  # hetzelfde formaat als de tekening van het wiel (900 × 500)


def _bijsnijden(img: Image.Image) -> Image.Image:
    """Altijd 9:5, het formaat van de wieltekening op de voorpagina. Vanuit het midden;
    van een staande foto blijft dus alleen een liggende strook over."""
    w, h = img.size
    doel = FORMAAT
    if w / h > doel:
        nw = round(h * doel)
        x = (w - nw) // 2
        return img.crop((x, 0, x + nw, h))
    nh = round(w / doel)
    y = (h - nh) // 2
    return img.crop((0, y, w, y + nh))


def ontwikkel(img: Image.Image, zaad: int) -> tuple[Image.Image, Image.Image]:
    """Geeft de grote plaat (lange zijde 1600) en een kleine (640) terug."""
    grijs = _bijsnijden(_grijs(img))
    grijs.thumbnail((1600, 1600), Image.LANCZOS)
    a = np.asarray(grijs, np.float32) / 255
    h, w = a.shape

    # niveaus: zwart echt zwart, de hoge lichten net niet wit
    lo, hi = np.percentile(a, 1.5), np.percentile(a, 99.6)
    a = np.clip((a - lo) / max(hi - lo, 1e-3), 0, 1)
    # schaduwen dieper, lichten blijven: een lichte S-curve met de nadruk onder
    a = a ** 1.45
    a = a * a * (3 - 2 * a) * .35 + a * .65
    # te licht? dan donkerder belichten (zoals een stop minder), richting DOEL_HELDERHEID.
    # Half lineair, half via de curve: de lichten zakken, de schaduwen houden tekening.
    m = float(a.mean())
    if m > DOEL_HELDERHEID:
        k = DOEL_HELDERHEID / m
        a = a * k ** .5 * (a ** (1 - k)) ** .5

    # vignet en schaduw van rechtsonder, dezelfde maten als de tekening van het wiel
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.hypot((xx / w - .40) / .68, (yy / h - .46) / .68) / 1.0
    vignet = np.interp(d, [0, .18, .62, 1.0, 9], [0, 0, .5, .9, .97])
    diag = ((xx / w - .25) + (yy / h - .15)) / ((1 - .25) + (1 - .15))
    schaduw = np.interp(diag, [0, .25, .55, 1], [0, 0, .45, .85])
    a = a * (1 - vignet) * (1 - schaduw)

    # korrel, sterker in de middentonen
    rng = np.random.default_rng(zaad)
    ruis = rng.normal(0, 1, (h, w)).astype(np.float32)
    ruis = cv2.GaussianBlur(ruis, (0, 0), .7)
    a = np.clip(a + ruis * .045 * (.35 + a * (1 - a) * 2.6), 0, 1)

    kleur = DONKER + a[..., None] * (LICHT - DONKER)
    groot = Image.fromarray((kleur * 255 + .5).astype(np.uint8), "RGB")
    klein = groot.copy()
    klein.thumbnail((640, 640), Image.LANCZOS)
    return groot, klein
