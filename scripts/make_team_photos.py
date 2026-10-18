"""Builds circular team photos with the name banded across the bottom: docs/deck/assets/team_<name>.png.
Usage: python scripts/make_team_photos.py <folder with abhi/rishub/jayanth/prateek .jpeg>"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Desktop/pics"
OUT = Path(__file__).resolve().parent.parent / "docs/deck/assets"
# file, display name, square crop box (left, top, size) chosen to keep the face centred
PEOPLE = [("abhi", "Abhishek", None), ("rishub", "Rishub", (0, 95, 755)),
          ("jayanth", "Jeyanth", None), ("prateek", "Pratheek", (50, 0, 750))]
SIZE = 700
font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 64, index=1)

for f, name, box in PEOPLE:
    im = Image.open(SRC / f"{f}.jpeg").convert("RGB")
    if box is None:
        s = min(im.size); box = ((im.width - s) // 2, (im.height - s) // 2, s)
    l, t, s = box
    im = im.crop((l, t, l + s, t + s)).resize((SIZE, SIZE), Image.LANCZOS).convert("RGBA")
    band = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(band)
    d.rectangle([0, int(SIZE * 0.74), SIZE, SIZE], fill=(20, 24, 31, 190))
    w = d.textlength(name, font=font)
    d.text(((SIZE - w) / 2, int(SIZE * 0.74) + (SIZE * 0.26 - 64) / 2 - 6), name, font=font, fill=(255, 255, 255, 255))
    im = Image.alpha_composite(im, band)
    mask = Image.new("L", im.size, 0); ImageDraw.Draw(mask).ellipse([0, 0, SIZE - 1, SIZE - 1], fill=255)
    im.putalpha(mask)
    im.save(OUT / f"team_{name.lower()}.png")
    print("wrote", f"team_{name.lower()}.png")
