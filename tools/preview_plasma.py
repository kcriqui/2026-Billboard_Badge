#!/usr/bin/env python3
"""Preview the Space Weather plasma on the laptop, using the badge's own code.

    python3 tools/preview_plasma.py            # live NOAA data + a storm
    python3 tools/preview_plasma.py --out /tmp/plasma

Runs firmware/badge/lib/plasma.py under CPython (viper/ptr stubs) and writes
<out>_calm.png, <out>_storm.png and <out>_ghosts.png (3 updates, older ones
grey to suggest e-paper ghosting) at exact badge size: view them at 100 %.
Prints white/red/black coverage. Tune numbers in plasma.from_weather().
Data: NOAA Space Weather Prediction Center. Needs Pillow (apt: python3-pil).
"""

import argparse
import array
import builtins
import json
import pathlib
import sys
import types
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
mp = types.ModuleType("micropython")
mp.viper = mp.native = lambda f: f
mp.const = lambda x: x
sys.modules["micropython"] = mp
builtins.ptr8 = lambda b: b
builtins.ptr32 = lambda b: b if isinstance(b, array.array) else memoryview(b).cast("I")
sys.path.insert(0, str(REPO / "firmware/badge/lib"))
import plasma  # noqa: E402

from PIL import Image  # noqa: E402

W, H = plasma.W, plasma.H
RED, BLACK, WHITE = (205, 25, 30), (0, 0, 0), (255, 255, 255)


def live_weather():
    ua = {"User-Agent": "BillboardBadge-preview/1.0"}
    get = lambda p: json.loads(urllib.request.urlopen(urllib.request.Request(
        "https://services.swpc.noaa.gov" + p, headers=ua), timeout=20).read())
    sp = get("/products/summary/solar-wind-speed.json")[0]
    mag = get("/products/summary/solar-wind-mag-field.json")[0]
    kp = get("/json/planetary_k_index_1m.json")[-1]
    g = int(get("/products/noaa-scales.json")["0"]["G"]["Scale"] or 0)
    return {"speed": sp["proton_speed"], "bt": mag["bt"], "bz": mag["bz_gsm"],
            "kp": kp["estimated_kp"], "g": g}


def frame(wx, step):
    blk = bytearray(W * H // 8)
    red = bytearray(W * H // 8)
    rp, bp = plasma.from_weather(wx, step)
    plasma.layer(red, rp)
    plasma.layer(blk, bp, avoid=red)
    return blk, red


def image(layers):
    im = Image.new("RGB", (W, H), WHITE)
    px = im.load()
    for (blk, red), age in layers:
        for i in range(W * H):
            m = 128 >> (i & 7)
            if red[i >> 3] & m and age == 0:
                px[i % W, i // W] = RED
            elif blk[i >> 3] & m:
                px[i % W, i // W] = BLACK if age == 0 else (150,) * 3 if age == 1 else (205,) * 3
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="plasma_preview")
    args = ap.parse_args()
    calm = live_weather()
    storm = {"speed": 700, "bt": 22, "bz": -15, "kp": 6.3, "g": 2}
    print("live:", calm)
    for name, layers in (("calm", [(frame(calm, 3), 0)]),
                         ("storm", [(frame(storm, 3), 0)]),
                         ("ghosts", [(frame(calm, 1), 2), (frame(calm, 2), 1), (frame(calm, 3), 0)])):
        im = image(layers)
        path = "%s_%s.png" % (args.out, name)
        im.save(path)
        px = list(im.getdata())
        n = len(px)
        print("%-6s white %2.0f%%  red %2.0f%%  black %2.0f%%  -> %s" % (
            name, 100 * px.count(WHITE) / n, 100 * px.count(RED) / n, 100 * px.count(BLACK) / n, path))


if __name__ == "__main__":
    main()
