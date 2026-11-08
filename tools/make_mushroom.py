#!/usr/bin/env python3
"""Draw WOPR's mushroom-cloud sprites (two growth stages) for the badge.

    python3 tools/make_mushroom.py [--preview out.png]

Writes firmware/badge/lib/sprite_mushroom.py: for each stage, a 1-bit MASK
(cloud silhouette: cleared to white on the panel) and INK (black pixels),
MONO_HLSB rows, plus the anchor (the ground point under the stem, which goes
on the target).

Modelled on photos of real test clouds (Wikipedia "Mushroom cloud": Nagasaki,
Buster-Jangle Charlie, Tumbler-Snapper Dog): a lumpy cauliflower cap much
wider than the stem, lit from above so the billow tops are bright and the
rolled-under bottom is dark; a narrow, irregular stem flaring at the foot
with a flat condensation ring partway up; a low, wide dust cloud at the base.

Each billow is shaded like a sphere lit from the upper left, in grey at 4x
on the laptop, then Atkinson-dithered at single-pixel resolution with a
1 px outline (Kevin chose 1 px over 2x2 cells; lone pixels can look pale
after a fast refresh). Needs Pillow.
"""

import argparse
import math
import pathlib
import random

from PIL import Image

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "firmware/badge/lib/sprite_mushroom.py"


LIGHT = (-0.45, -0.75, 0.48)   # from the upper left, towards the viewer


def _norm(v):
    n = sum(c * c for c in v) ** 0.5
    return tuple(c / n for c in v)


def sphere(px, mk, Sx, Sy, cx, cy, r, lo, hi, squash=1.0):
    """Paint a sphere-lit billow (brightness lo..hi) into the grey grid."""
    lx, ly, lz = _norm(LIGHT)
    ry = r * squash
    for y in range(max(0, int(cy - ry)), min(Sy, int(cy + ry) + 1)):
        dy = (y - cy) / ry
        for x in range(max(0, int(cx - r)), min(Sx, int(cx + r) + 1)):
            dx = (x - cx) / r
            q = dx * dx + dy * dy
            if q > 1:
                continue
            nz = (1 - q) ** 0.5
            lam = max(0.0, dx * lx + dy * ly + nz * lz)
            px[y][x] = lo + (hi - lo) * lam
            mk[y][x] = 1


def draw_cloud(w, h, stage, seed=7):
    """Grey cloud (0 black .. 255 white) and silhouette, at 4x panel size."""
    k = 4
    Sx, Sy = w * k, h * k
    rnd = random.Random(seed * 10 + stage)
    px = [[255.0] * Sx for _ in range(Sy)]
    mk = [[0] * Sx for _ in range(Sy)]
    cx, ground = Sx / 2, Sy - 2 * k
    if stage == 1:   # young: billowing fireball on a short stem, dust starting
        cap = (Sy * 0.42, Sx * 0.30, Sy * 0.22)   # centre y, half width, half height
        stem_w0, stem_w1 = Sx * 0.05, Sx * 0.09
        base = (Sx * 0.26, Sx * 0.07)
        ring = None
    else:            # full mushroom: wide cap, tall stem, ring, wide base surge
        cap = (Sy * 0.20, Sx * 0.43, Sy * 0.15)
        stem_w0, stem_w1 = Sx * 0.06, Sx * 0.13
        base = (Sx * 0.36, Sx * 0.075)
        ring = (Sy * 0.58, Sx * 0.24)
    cap_y, cap_rx, cap_ry = cap
    # base surge: flattened billows along the ground
    for i in range(14):
        f = (i / 13) * 2 - 1
        bx = cx + f * base[0] + rnd.uniform(-1, 1) * k
        r = base[1] * rnd.uniform(0.75, 1.25) * (1.35 - 0.6 * abs(f))   # domed in the middle
        sphere(px, mk, Sx, Sy, bx, ground - r * 0.85, r * 1.15, 70, 230, squash=0.85)
    # stem: shaded like a cylinder, wavy, flaring at the foot
    top, bot = cap_y + cap_ry * 0.7, ground - base[1] * 0.8
    for y in range(int(top), int(bot)):
        t = max(0.0, (y - top) / (bot - top))
        w = stem_w0 + (stem_w1 - stem_w0) * t ** 2.5
        c = cx + math.sin(t * 6.0 + stage) * k * 0.9
        for x in range(int(c - w), int(c + w) + 1):
            u = (x - c) / w
            lam = max(0.0, -u * 0.6 + 0.55)
            px[y][x] = 60 + 150 * lam
            mk[y][x] = 1
    if ring:         # condensation ring: thin flat disc around the stem
        ry_, rrx = ring
        for y in range(int(ry_ - k * 2), int(ry_ + k * 2)):
            for x in range(int(cx - rrx), int(cx + rrx)):
                q = ((x - cx) / rrx) ** 2 + ((y - ry_) / (k * 2)) ** 2
                if q <= 1:
                    px[y][x] = 225 if y < ry_ else 120
                    mk[y][x] = 1
    # cap: dark rolled-under band, then billows from the back/top down
    for y in range(int(cap_y), int(cap_y + cap_ry * 1.05)):
        for x in range(int(cx - cap_rx), int(cx + cap_rx)):
            q = ((x - cx) / (cap_rx * 0.97)) ** 2 + ((y - cap_y) / (cap_ry * 1.05)) ** 2
            if q <= 1:
                px[y][x] = 55 + 40 * (1 - q)
                mk[y][x] = 1
    blobs = []
    for i in range(30):
        a = rnd.uniform(math.pi * 0.95, math.pi * 2.05)  # upper half outline
        rr = rnd.uniform(0.7, 1.08)                      # out to the edge: lumpy rim
        bx = cx + math.cos(a) * cap_rx * 0.82 * rr
        by = cap_y + math.sin(a) * cap_ry * 0.95 * rr
        blobs.append((by, bx, cap_ry * rnd.uniform(0.30, 0.62)))
    for i in range(9):                                   # roll along the bottom edge
        f = (i / 8) * 2 - 1
        blobs.append((cap_y + cap_ry * 0.55, cx + f * cap_rx * 0.85, cap_ry * 0.42))
    blobs.sort()                                         # top first, lower in front
    for by, bx, r in blobs:
        dark = by > cap_y + cap_ry * 0.3
        sphere(px, mk, Sx, Sy, bx, by, r, 35 if dark else 95, 215 if dark else 255)
    grey = Image.new("L", (Sx, Sy))
    grey.putdata([int(v) for row in px for v in row])
    mask = Image.new("L", (Sx, Sy))
    mask.putdata([255 * v for row in mk for v in row])
    return grey, mask


def to_panel(grey, mask, w, h):
    """Downscale to panel pixels: Atkinson-dithered at single-pixel
    resolution (Kevin: no 2x2 cells) with a 1 px outline."""
    g = grey.resize((w, h), Image.BOX)
    mh = mask.resize((w, h), Image.BOX)
    gv = [[float(g.getpixel((x, y))) for x in range(w)] for y in range(h)]
    mv = [[mh.getpixel((x, y)) > 100 for x in range(w)] for y in range(h)]
    ink = Image.new("1", (w, h), 0)
    msk = Image.new("1", (w, h), 0)
    ip, mp = ink.load(), msk.load()
    for y in range(h):
        for x in range(w):
            if not mv[y][x]:
                continue
            mp[x, y] = 1
            edge = any(not (0 <= x + dx < w and 0 <= y + dy < h and mv[y + dy][x + dx])
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            old = gv[y][x]
            new = 0 if (old < 128 or edge) else 255
            if new == 0:
                ip[x, y] = 1
            err = (old - new) / 8
            for dx, dy in ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and yy < h and mv[yy][xx]:
                    gv[yy][xx] += err
    return msk, ink


def pack(img):
    w, h = img.size
    px = img.load()
    out = bytearray()
    for y in range(h):
        for bx in range((w + 7) // 8):
            b = 0
            for bit in range(8):
                x = bx * 8 + bit
                if x < w and px[x, y]:
                    b |= 0x80 >> bit
            out.append(b)
    return bytes(out)


SIZES = {1: (32, 32), 2: (32, 48)}   # full cloud grows taller, not wider (Kevin)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preview", help="also write a zoomed preview PNG")
    args = ap.parse_args()
    stages = {}
    for stage, (w, h) in SIZES.items():
        grey, mask = draw_cloud(w, h, stage)
        stages[stage] = to_panel(grey, mask, w, h)
    with open(OUT, "w") as f:
        f.write('"""Mushroom-cloud sprites for WOPR, made by tools/make_mushroom.py; do not edit.\n\n'
                'STAGES[n] = (width, height, anchor_x, anchor_y, MASK, INK): MONO_HLSB rows;\n'
                'MASK = silhouette (clear to white), INK = black pixels. The anchor (ground\n'
                'under the stem) goes on the target.\n"""\n\n')
        f.write("STAGES = {\n")
        for stage, (mk, ink) in stages.items():
            w, h = SIZES[stage]
            f.write("    %d: (%d, %d, %d, %d,\n        %r,\n        %r),\n" % (
                stage, w, h, w // 2, h - 3, pack(mk), pack(ink)))
        f.write("}\n")
    print("wrote", OUT)
    if args.preview:
        tiles = []
        for stage, (mk, ink) in stages.items():
            t = Image.new("RGB", mk.size, (255, 255, 255))
            t.paste((0, 0, 0), mask=ink)
            tiles.append(t.resize((t.width * 5, t.height * 5), Image.NEAREST))
        sheet = Image.new("RGB", (sum(t.width for t in tiles) + 40, max(t.height for t in tiles) + 20), (200, 200, 200))
        x = 10
        for t in tiles:
            sheet.paste(t, (x, sheet.height - t.height - 10))
            x += t.width + 20
        sheet.save(args.preview)


if __name__ == "__main__":
    main()
