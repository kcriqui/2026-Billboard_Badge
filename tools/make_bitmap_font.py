#!/usr/bin/env python3
"""Render a TrueType font into a 1-bit bitmap font module for the badge.

    python3 tools/make_bitmap_font.py --size 18   # alt text: DejaVu Sans 18 px -> lib/font_alt.py
    python3 tools/make_bitmap_font.py --font F.ttf --size 16 --name font_x
    python3 tools/make_bitmap_font.py --font .../DejaVuSans-ExtraLight.ttf \
        --size 44 --name font_thin --stroke 2    # WOPR banner: even 2 px pen

--stroke N redraws each letter as a pen stroke exactly N panel pixels wide,
like the vector lettering of the film's screens: the glyph is rendered at
STROKE_SCALE x size, thinned to a 1 px centreline (Zhang-Suen), scaled back
and stamped with an N x N pen. Hinting a hairline font gave a mix of 1 and
2 px strokes (and 1 px strokes stay pale after the panel's fast refresh);
--dilate (thicken by 1 px) still left 2 vs 3 px. Pure Python, no numpy.

Glyphs are rendered on the laptop with hinting and no anti-aliasing (Pillow
fontmode "1"), so every stroke lands on whole pixels — crisper on the panel
than LVGL's anti-aliased fonts, which the badge has to threshold. Drawn by
lib/bitfont.py. Covers printable ASCII; bitfont maps common Unicode
punctuation (curly quotes, dashes, ellipsis) to ASCII.
Needs Pillow (apt: python3-pil).
"""

import argparse
import pathlib

from PIL import Image, ImageChops, ImageDraw, ImageFont

REPO = pathlib.Path(__file__).resolve().parent.parent
FIRST, LAST = 32, 126


STROKE_SCALE = 4


def _thin(px, w, h):
    """Zhang-Suen thinning of a 0/1 grid (list of rows), in place."""
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            kill = []
            for y in range(1, h - 1):
                r0, r1, r2 = px[y - 1], px[y], px[y + 1]
                for x in range(1, w - 1):
                    if not r1[x]:
                        continue
                    p2, p3, p4, p5 = r0[x], r0[x + 1], r1[x + 1], r2[x + 1]
                    p6, p7, p8, p9 = r2[x], r2[x - 1], r1[x - 1], r0[x - 1]
                    n = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
                    if n < 2 or n > 6:
                        continue
                    seq = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
                    if sum(1 for i in range(8) if seq[i] == 0 and seq[i + 1] == 1) != 1:
                        continue
                    if step == 0 and (p2 * p4 * p6 or p4 * p6 * p8):
                        continue
                    if step == 1 and (p2 * p4 * p8 or p2 * p6 * p8):
                        continue
                    kill.append((x, y))
            for x, y in kill:
                px[y][x] = 0
            changed = changed or bool(kill)


_big_fonts = {}


def stroke_glyph(path, size, ch, w, height, ascent, pen):
    """Glyph as an even `pen`-px stroke along its centreline."""
    k = STROKE_SCALE
    big = _big_fonts.get((path, size)) or _big_fonts.setdefault(
        (path, size), ImageFont.truetype(path, size * k))
    bw, bh = (w + 2) * k, (height + 2) * k
    im = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(im).text((k, (ascent + 1) * k), ch, font=big, fill=255, anchor="ls")
    data = im.load()
    px = [[1 if data[x, y] > 127 else 0 for x in range(bw)] for y in range(bh)]
    _thin(px, bw, bh)
    out = Image.new("1", (w, height), 0)
    o = out.load()
    half = pen / 2
    for y in range(bh):
        for x in range(bw):
            if px[y][x]:
                cx = int((x - k) / k + 0.5 - half + 0.5)
                cy = int((y - k) / k + 0.5 - half + 0.5)
                for dy in range(pen):
                    for dx in range(pen):
                        if 0 <= cx + dx < w and 0 <= cy + dy < height:
                            o[cx + dx, cy + dy] = 1
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--font", default="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    ap.add_argument("--size", type=int, default=15)
    ap.add_argument("--name", default="font_alt")
    ap.add_argument("--dilate", action="store_true", help="thicken strokes by 1 px")
    ap.add_argument("--stroke", type=int, default=0, help="redraw glyphs as an N px pen along their centreline")
    args = ap.parse_args()

    font = ImageFont.truetype(args.font, args.size)
    ascent, descent = font.getmetrics()
    height = ascent + descent
    data = bytearray()
    offsets, widths, adv16 = [], [], []
    for code in range(FIRST, LAST + 1):
        ch = chr(code)
        # Advance in 1/16 px: the drawer keeps a fractional pen position, as
        # FreeType does, so per-letter rounding doesn't make spacing uneven.
        exact = font.getlength(ch, mode="1")
        adv = round(exact)
        left, _, right, _ = font.getbbox(ch, anchor="ls")
        w = max(adv, right, 1) + (1 if args.dilate else 0) + args.stroke
        if args.stroke:
            img = stroke_glyph(args.font, args.size, ch, w, height, ascent, args.stroke)
        else:
            img = Image.new("1", (w, height), 0)
            d = ImageDraw.Draw(img)
            d.fontmode = "1"  # hinted, no anti-aliasing
            d.text((0, ascent), ch, font=font, fill=1, anchor="ls")
        if args.dilate:
            g = img.convert("L")
            out = g
            for dx, dy in ((1, 0), (0, 1), (1, 1)):
                out = ImageChops.lighter(out, ImageChops.offset(g, dx, dy))
            img = out.convert("1")
        row_bytes = (w + 7) // 8
        offsets.append(len(data))
        widths.append(w)
        adv16.append(round(exact * 16))
        px = img.load()
        for y in range(height):
            for bx in range(row_bytes):
                b = 0
                for bit in range(8):
                    x = bx * 8 + bit
                    if x < w and px[x, y]:
                        b |= 0x80 >> bit
                data.append(b)

    out = REPO / "firmware/badge/lib" / f"{args.name}.py"
    with open(out, "w") as f:
        f.write(f'"""1-bit bitmap font: {pathlib.Path(args.font).stem} {args.size} px.\n\n'
                f'Generated by tools/make_bitmap_font.py; do not edit. Drawn by lib/bitfont.py.\n"""\n\n')
        f.write(f"HEIGHT = {height}\nASCENT = {ascent}\nFIRST = {FIRST}\nLAST = {LAST}\n")
        f.write(f"OFFSETS = {tuple(offsets)}\n")
        f.write(f"WIDTHS = bytes({bytes(widths)!r})\n")
        f.write(f"ADV16 = {tuple(adv16)}  # advance widths in 1/16 px\n")
        f.write(f"DATA = {bytes(data)!r}\n")
    print(f"wrote {out.relative_to(REPO)}: height {height}, {len(data)} bytes of glyphs")


if __name__ == "__main__":
    main()
