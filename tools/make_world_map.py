#!/usr/bin/env python3
"""Render the red world map used by the badge's Earth app.

    python3 tools/make_world_map.py                  # outline style
    python3 tools/make_world_map.py --style fill
    python3 tools/make_world_map.py --projection polar   # WOPR polar board

Polar (firmware/badge/data/earth/polar.png, 960 x 480): azimuthal
equidistant around the North Pole down to POLAR_MIN_LAT at the rim, North
America at the bottom; red coastlines plus black rim, dotted latitude rings
and dotted spokes. apps/earth.py uses the same POLAR_* constants - keep
them in step.

Output: firmware/badge/data/earth/world.png — 960 x 480, equirectangular
(longitude -180..180 across, latitude 90..-90 down), white background with
red land, palette PNG with only white/black/red as the panel needs.

Map data: Made with Natural Earth. Free vector and raster map data @
naturalearthdata.com (public domain). Uses ne_110m_land.geojson, which is
not committed; fetch it with:
    gh api -H "Accept: application/vnd.github.raw" \\
      repos/nvkelso/natural-earth-vector/contents/geojson/ne_110m_land.geojson \\
      > tools/data/ne_110m_land.geojson
Needs Pillow (apt: python3-pil).
"""

import argparse
import json
import math
import pathlib

from PIL import Image, ImageDraw

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "tools/data/ne_110m_land.geojson"
OUT = REPO / "firmware/badge/data/earth/world.png"
W, H = 960, 480
PALETTE = [255, 255, 255, 0, 0, 0, 255, 0, 0]  # 0 white, 1 black, 2 red


POLAR_OUT = REPO / "firmware/badge/data/earth/polar.png"
POLAR_CX, POLAR_CY, POLAR_R, POLAR_MIN_LAT, POLAR_LON0 = 480, 240, 238, -20, -100


def polar(lon, lat):
    r = (90 - lat) / (90 - POLAR_MIN_LAT) * POLAR_R
    t = math.radians(lon - POLAR_LON0)
    return POLAR_CX + r * math.sin(t), POLAR_CY + r * math.cos(t)


def render_polar(width=2):
    img = Image.new("P", (W, H), 0)
    img.putpalette(PALETTE + [0] * (768 - len(PALETTE)))
    draw = ImageDraw.Draw(img)
    for lat in (60, 30, 0):                       # dotted rings
        r = (90 - lat) / (90 - POLAR_MIN_LAT) * POLAR_R
        for k in range(0, 360, 2):
            t = math.radians(k)
            draw.point((POLAR_CX + r * math.sin(t), POLAR_CY + r * math.cos(t)), fill=1)
    for lon in range(-180, 180, 30):              # dotted spokes
        x, y = polar(lon, POLAR_MIN_LAT)
        for i in range(0, 60, 2):
            draw.point((POLAR_CX + (x - POLAR_CX) * i / 60, POLAR_CY + (y - POLAR_CY) * i / 60), fill=1)
    draw.ellipse((POLAR_CX - POLAR_R, POLAR_CY - POLAR_R, POLAR_CX + POLAR_R, POLAR_CY + POLAR_R),
                 outline=1, width=2)
    for feature in json.load(open(SRC))["features"]:
        geom = feature["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = poly[0]
            for (a, b), (c, d) in zip(ring, ring[1:] + ring[:1]):
                if b >= POLAR_MIN_LAT and d >= POLAR_MIN_LAT:
                    draw.line([polar(a, b), polar(c, d)], fill=2, width=width)
    return img


def project(lon, lat):
    return (lon + 180) * W / 360, (90 - lat) * H / 180


def render(style, width=2):
    img = Image.new("P", (W, H), 0)
    img.putpalette(PALETTE + [0] * (768 - len(PALETTE)))
    draw = ImageDraw.Draw(img)
    for feature in json.load(open(SRC))["features"]:
        geom = feature["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = [project(lon, lat) for lon, lat in poly[0]]
            if style == "fill":
                draw.polygon(ring, fill=2)
            else:
                draw.line(ring + ring[:1], fill=2, width=width)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--style", choices=("outline", "fill"), default="outline")
    ap.add_argument("--width", type=int, default=2, help="outline width in px")
    ap.add_argument("--projection", choices=("world", "polar"), default="world")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    polar_map = args.projection == "polar"
    out = pathlib.Path(args.out or (POLAR_OUT if polar_map else OUT))
    out.parent.mkdir(parents=True, exist_ok=True)
    img = render_polar(args.width) if polar_map else render(args.style, args.width)
    img.save(out, optimize=True)
    print("wrote", out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
