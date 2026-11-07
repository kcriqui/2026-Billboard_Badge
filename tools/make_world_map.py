#!/usr/bin/env python3
"""Render the red world map used by the badge's Earth app.

    python3 tools/make_world_map.py                  # outline style
    python3 tools/make_world_map.py --style fill

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
import pathlib

from PIL import Image, ImageDraw

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "tools/data/ne_110m_land.geojson"
OUT = REPO / "firmware/badge/data/earth/world.png"
W, H = 960, 480
PALETTE = [255, 255, 255, 0, 0, 0, 255, 0, 0]  # 0 white, 1 black, 2 red


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
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    render(args.style, args.width).save(out, optimize=True)
    print("wrote", out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
