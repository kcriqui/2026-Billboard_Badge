#!/usr/bin/env python3
"""Write a name into the blank "Hello I am..." tag for the badge's Nametag app.

    python3 tools/make_nametag.py Kevin
    python3 tools/make_nametag.py "Ada L." --height 90 --font /path/to/font.ttf

Output: firmware/badge/data/graphics/hello_i_am_<name>.png (plus a copy in
assets/graphics/). The Nametag app shows any hello_i_am_<name>.png in
place of the blank tag. Push it with: cd firmware && ./dev.sh push

Pixels are only white, black or red (no anti-aliasing), as the panel shows.

Default font: xkcd Script (https://github.com/ipython/xkcd-font, CC BY-NC 3.0).
It isn't in apt and isn't committed here; fetch it with:
    gh api -H "Accept: application/vnd.github.raw" \
      repos/ipython/xkcd-font/contents/xkcd-script/font/xkcd-script.ttf \
      > tools/fonts/xkcd-script.ttf
Needs Pillow (apt: python3-pil).
"""

import argparse
import pathlib

from PIL import Image, ImageDraw, ImageFont

REPO = pathlib.Path(__file__).resolve().parent.parent
BLANK = REPO / "firmware/badge/data/graphics/hello_i_am_blank.png"
TOP, BOTTOM = 221, 557  # the white band in the blank tag
PALETTE = [255, 255, 255, 0, 0, 0, 255, 0, 0]  # white, black, red


def make(name, font_path, height, stroke):
    base = Image.open(BLANK).convert("RGB")
    probe = ImageDraw.Draw(base)
    size = 20
    while True:  # grow the font until the name is `height` px tall
        font = ImageFont.truetype(str(font_path), size)
        l, t, r, b = probe.textbbox((0, 0), name, font=font, stroke_width=stroke)
        if b - t >= height:
            break
        size += 2
    if r - l > base.width - 40:
        raise SystemExit(f"'{name}' is {r - l}px wide at this height; try a smaller --height")
    mask = Image.new("1", base.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.fontmode = "1"  # no anti-aliasing
    x = (base.width - (r - l)) // 2 - l
    y = (TOP + BOTTOM) // 2 - (t + b) // 2
    draw.text((x, y), name, fill=1, font=font, stroke_width=stroke, stroke_fill=1)
    base.paste((0, 0, 0), (0, 0), mask)
    pal = Image.new("P", (1, 1))
    pal.putpalette(PALETTE + [0] * (768 - len(PALETTE)))
    return base.quantize(palette=pal, dither=Image.Dither.NONE)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name")
    ap.add_argument("--font", default=REPO / "tools/fonts/xkcd-script.ttf")
    ap.add_argument("--height", type=int, default=116, help="text height in pixels (default 116)")
    ap.add_argument("--stroke", type=int, default=0, help="extra pen thickness in pixels")
    args = ap.parse_args()
    img = make(args.name, args.font, args.height, args.stroke)
    slug = "".join(c for c in args.name.lower() if c.isalnum()) or "name"
    for folder in ("firmware/badge/data/graphics", "assets/graphics"):
        out = REPO / folder / f"hello_i_am_{slug}.png"
        img.save(out, optimize=True)
        print("wrote", out.relative_to(REPO))


if __name__ == "__main__":
    main()
