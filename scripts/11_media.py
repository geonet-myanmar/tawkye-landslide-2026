"""Before/after frame pairs from IMG_4514.MOV and a web copy of the oblique photo.

The video is a GSM/TSBM Google Earth fly-through (caption: Taw Kye landslide of
26.9.2026, compiled 2.10.2026). It alternates Google Earth imagery dated 12/1/2023
(pre-event) with the same view with the drone orthomosaics draped on it (post-event),
so matching frames make before/after pairs. Not georeferenced - illustration only.
"""
from pathlib import Path
import cv2
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
PAIRS = {"oblique": (0.0, 3.7), "south": (11.2, 13.1), "north": (16.8, 18.7)}


def frame(cap, t):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, f = cap.read()
    assert ok, t
    return Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))


def main():
    OUT.mkdir(exist_ok=True)
    cap = cv2.VideoCapture(str(ROOT / "IMG_4514.MOV"))
    for name, (tb, ta) in PAIRS.items():
        for tag, t in (("before", tb), ("after", ta)):
            im = frame(cap, t)
            im = im.resize((1280, round(im.height * 1280 / im.width)), Image.LANCZOS)
            im.save(OUT / f"video_{name}_{tag}.jpg", quality=82, optimize=True)
    Image.open(ROOT / "photo_2026-10-03_08-50-39.jpg").save(OUT / "oblique_photo.jpg", quality=85, optimize=True)
    print(sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
