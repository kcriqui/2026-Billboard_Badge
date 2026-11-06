#!/usr/bin/env python3
"""Turn a photo into a 960x672 white/black/red image for the badge (Nametag app).

    python3 tools/make_photo.py ~/Pictures/me.jpg kevin
    python3 tools/make_photo.py me.jpg kevin --bw --centre 0.5,0.4

Output: firmware/badge/data/photos/<name>.png. Push with: cd firmware && ./dev.sh push

The photo is cropped to the panel's shape, contrast-stretched and sharpened,
then Atkinson-dithered to the panel's three colours. Atkinson keeps more
contrast in faces than Floyd-Steinberg (which washes them out on this panel).
Needs Pillow (apt: python3-pil). Takes ~10 s.
"""

import argparse
import pathlib

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

REPO = pathlib.Path(__file__).resolve().parent.parent
W, H = 960, 672
WHITE, BLACK = (255, 255, 255), (0, 0, 0)
RED_LOOK = (200, 20, 30)  # what the panel's red looks like, for error diffusion
ATKINSON = ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2))


def prepare(path, centre):
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")  # phone photos: honour rotation
    img = ImageOps.fit(img, (W, H), Image.LANCZOS, centering=centre)
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    return img.filter(ImageFilter.UnsharpMask(2, 80, 2))


def atkinson(img, palette):
    """Atkinson error diffusion; returns palette indices row by row."""
    w, h = img.size
    px = [[list(img.getpixel((x, y))) for x in range(w)] for y in range(h)]
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            r, g, b = px[y][x]
            i = min(range(len(palette)), key=lambda k: (palette[k][0] - r) ** 2 * 0.3
                    + (palette[k][1] - g) ** 2 * 0.59 + (palette[k][2] - b) ** 2 * 0.11)
            out[y * w + x] = i
            c = palette[i]
            er, eg, eb = (r - c[0]) / 8, (g - c[1]) / 8, (b - c[2]) / 8
            for dx, dy in ATKINSON:
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and yy < h:
                    q = px[yy][xx]
                    q[0] += er
                    q[1] += eg
                    q[2] += eb
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("photo")
    ap.add_argument("name", help="output name, e.g. kevin -> data/photos/kevin.png")
    ap.add_argument("--bw", action="store_true", help="black and white only (no red)")
    ap.add_argument("--centre", default="0.5,0.45",
                    help="crop centre as x,y fractions (default 0.5,0.45)")
    args = ap.parse_args()

    centre = tuple(float(v) for v in args.centre.split(","))
    img = prepare(args.photo, centre)
    if args.bw:
        img = ImageOps.grayscale(img).convert("RGB")
    palette = [WHITE, BLACK] if args.bw else [WHITE, BLACK, RED_LOOK]
    indices = atkinson(img, palette)

    out = Image.frombytes("P", (W, H), bytes(indices))
    # Badge rule: red if R>127 and G,B<128; black if all <128; else white.
    out.putpalette([255, 255, 255, 0, 0, 0, 255, 0, 0] + [0] * (768 - 9))
    dest = REPO / "firmware/badge/data/photos" / f"{args.name}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, optimize=True)
    print("wrote", dest.relative_to(REPO), dest.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
