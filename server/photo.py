# The photograph: checking and developing.
#
# check()    is there a face in it? Then it is not published.
# develop()  turns it into a plate in the style of the site: black and white, deep shadows,
#            a vignette like the wheel drawing, and grain. Bright photos are first
#            "exposed" darker, so every plate ends up equally dark.
#            The result is a new file without metadata: no GPS, no camera.

import io
import os
from fractions import Fraction

import cv2
import numpy as np
from PIL import Image, ImageOps

try:  # photos from some Android phones are HEIC
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_detection_yunet_2023mar.onnx")
# how bright a plate may be on average before vignette and grain; brighter photos are darkened
TARGET_BRIGHTNESS = float(os.environ.get("TARGET_BRIGHTNESS", "0.3"))

DARK = np.array([0x0C, 0x0B, 0x0A], np.float32) / 255    # the black plate of the site
LIGHT = np.array([0xDC, 0xD5, 0xC7], np.float32) / 255   # the line colour of the drawing

Image.MAX_IMAGE_PIXELS = 80_000_000


class Rejected(Exception):
    """The photo does not go online. The reason is short and readable, for the phone notification."""


def open_photo(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise Rejected("not an image")
    return img


def details(img: Image.Image) -> dict:
    """Shutter speed, ISO and the time of day (no date). Nothing else."""
    out = {}
    try:
        exif = img.getexif().get_ifd(0x8769)
    except Exception:
        return out
    t = exif.get(33434)  # ExposureTime
    if t:
        t = float(t)
        if t > 0:
            out["shutter"] = f"{t:g} s" if t >= 1 else f"1/{round(1 / t)} s"
    iso = exif.get(34855)  # ISOSpeedRatings
    if isinstance(iso, (tuple, list)):
        iso = iso[0] if iso else None
    if iso:
        out["iso"] = int(iso)
    moment = exif.get(36867) or exif.get(36868)  # DateTimeOriginal / Digitized: "2026:10:04 23:52:10"
    if isinstance(moment, str) and len(moment) >= 16:
        out["time"] = moment[11:16]
    return out


def _grey(img: Image.Image) -> Image.Image:
    return ImageOps.exif_transpose(img).convert("L")


_detector = None


def _faces(img: Image.Image) -> int:
    """Counts faces with YuNet. Looks twice: as the photo is, and brightened
    (in dark photos the model otherwise sees too little)."""
    global _detector
    rgb = np.asarray(ImageOps.exif_transpose(img).convert("RGB"))
    h, w = rgb.shape[:2]
    scale = min(1.0, 1280 / max(h, w))
    if scale < 1:
        rgb = cv2.resize(rgb, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    bright = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(MODEL, "", (320, 320), 0.6, 0.3, 5000)
    total = 0
    for frame in (bgr, bright):
        _detector.setInputSize((frame.shape[1], frame.shape[0]))
        _, found = _detector.detect(frame)
        total = max(total, 0 if found is None else len(found))
    return total


def check(img: Image.Image) -> None:
    if _faces(img):
        raise Rejected("face detected")


ASPECT = Fraction(9, 5)  # the same format as the wheel drawing (900 × 500)


def _crop(img: Image.Image) -> Image.Image:
    """Always 9:5, the format of the wheel drawing on the front page. From the centre,
    so a portrait photo keeps only a landscape strip."""
    w, h = img.size
    if w / h > ASPECT:
        nw = round(h * ASPECT)
        x = (w - nw) // 2
        return img.crop((x, 0, x + nw, h))
    nh = round(w / ASPECT)
    y = (h - nh) // 2
    return img.crop((0, y, w, y + nh))


def develop(img: Image.Image, seed: int) -> tuple[Image.Image, Image.Image]:
    """Returns the large plate (long side 1600) and a small one (640)."""
    grey = _crop(_grey(img))
    grey.thumbnail((1600, 1600), Image.LANCZOS)
    a = np.asarray(grey, np.float32) / 255
    h, w = a.shape

    # levels: black truly black, the highlights just short of white
    lo, hi = np.percentile(a, 1.5), np.percentile(a, 99.6)
    a = np.clip((a - lo) / max(hi - lo, 1e-3), 0, 1)
    # deeper shadows, highlights stay: a gentle S-curve weighted towards the bottom
    a = a ** 1.45
    a = a * a * (3 - 2 * a) * .35 + a * .65
    # too bright? then expose darker (like a stop down), towards TARGET_BRIGHTNESS.
    # Half linear, half through the curve: highlights drop, shadows keep detail.
    m = float(a.mean())
    if m > TARGET_BRIGHTNESS:
        k = TARGET_BRIGHTNESS / m
        a = a * k ** .5 * (a ** (1 - k)) ** .5

    # vignette and shadow from the bottom right, same proportions as the wheel drawing
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.hypot((xx / w - .40) / .68, (yy / h - .46) / .68) / 1.0
    vignette = np.interp(d, [0, .18, .62, 1.0, 9], [0, 0, .5, .9, .97])
    diag = ((xx / w - .25) + (yy / h - .15)) / ((1 - .25) + (1 - .15))
    shadow = np.interp(diag, [0, .25, .55, 1], [0, 0, .45, .85])
    a = a * (1 - vignette) * (1 - shadow)

    # grain, stronger in the midtones
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, (h, w)).astype(np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), .7)
    a = np.clip(a + noise * .045 * (.35 + a * (1 - a) * 2.6), 0, 1)

    colour = DARK + a[..., None] * (LIGHT - DARK)
    large = Image.fromarray((colour * 255 + .5).astype(np.uint8), "RGB")
    small = large.copy()
    small.thumbnail((640, 640), Image.LANCZOS)
    return large, small
