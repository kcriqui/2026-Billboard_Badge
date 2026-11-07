#!/usr/bin/env python3
"""Preview a WarGames-style "war room" layer for Long Exposure Earth.

    python3 tools/preview_earth_wopr.py out.png

Renders the real map (firmware/badge/data/earth/world.png) at 960x672 with
simulated missile arcs, ISS track and quakes after an hour of 3-minute
updates. Things no longer drawn are shown as fading grey ghosts, roughly
how the panel's fast refresh leaves them. Two variants side by side:
  A  overlay: arcs + DEFCON line on the current layout
  B  war room: dotted lat/lon grid, monospace text, DEFCON box
Needs Pillow.
"""

import math
import pathlib
import random
import sys

from PIL import Image, ImageDraw, ImageFont

REPO = pathlib.Path(__file__).resolve().parent.parent
W, H = 960, 672
MAP_Y, MAP_W, MAP_H = 96, 960, 480
RED, BLACK, WHITE = (205, 25, 30), (0, 0, 0), (255, 255, 255)
DJ = "/usr/share/fonts/truetype/dejavu/"

# Launch sites and targets: just cities (lon, lat), nothing real implied.
CITIES = {
    "SEATTLE": (-122.3, 47.6), "DENVER": (-105.0, 39.7), "CHICAGO": (-87.6, 41.9),
    "NEW YORK": (-74.0, 40.7), "LOS ANGELES": (-118.2, 34.1), "ANCHORAGE": (-149.9, 61.2),
    "LONDON": (-0.1, 51.5), "PARIS": (2.4, 48.9), "BERLIN": (13.4, 52.5),
    "MOSCOW": (37.6, 55.8), "MURMANSK": (33.1, 69.0), "NOVOSIBIRSK": (82.9, 55.0),
    "VLADIVOSTOK": (131.9, 43.1), "BEIJING": (116.4, 39.9), "TOKYO": (139.7, 35.7),
    "HONOLULU": (-157.9, 21.3), "SAO PAULO": (-46.6, -23.5), "SYDNEY": (151.2, -33.9),
}
SIDES = (["SEATTLE", "DENVER", "CHICAGO", "NEW YORK", "LOS ANGELES", "ANCHORAGE",
          "LONDON", "PARIS", "HONOLULU"],
         ["MOSCOW", "MURMANSK", "NOVOSIBIRSK", "VLADIVOSTOK", "BEIJING", "BERLIN"])


def xy(lon, lat):
    return (lon + 180) * MAP_W / 360, MAP_Y + (90 - lat) * MAP_H / 180


def arc_points(a, b, n=60):
    """Ballistic-looking arc: a quadratic curve bulging up (north) by a third
    of its length. Crossings wider than half the map go the short way round
    the date line, drawn in two pieces."""
    (x0, y0), (x2, y2) = xy(*CITIES[a]), xy(*CITIES[b])
    if abs(x2 - x0) > MAP_W / 2:
        x2 += -MAP_W if x2 > x0 else MAP_W
    d = math.hypot(x2 - x0, y2 - y0)
    cx, cy = (x0 + x2) / 2, min(y0, y2) - d / 4
    cy = max(cy, MAP_Y + 30)
    pts = []
    for i in range(n + 1):
        t = i / n
        x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x2
        y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y2
        pts.append((x % MAP_W, y))
    return pts


def missiles(seed, steps):
    """[(launch_step, flight_steps, a, b)]: salvos from both sides."""
    rnd = random.Random(seed)
    out = []
    for s in range(0, steps, 3):
        for _ in range(rnd.choice((1, 2, 2, 3))):
            side = rnd.randrange(2)
            out.append((s + rnd.randrange(3), rnd.randrange(7, 12),
                        rnd.choice(SIDES[side]), rnd.choice(SIDES[1 - side])))
    return out


def draw_frame(step, msl, quakes, iss, variant):
    """Black marks for one update: list of (kind, data)."""
    marks = []
    for launch, flight, a, b in msl:
        age = step - launch
        if age < 0:
            continue
        pts = arc_points(a, b)
        if age <= flight:
            k = int(len(pts) * age / flight)
            marks.append(("arc", pts[:max(k, 2)]))
            marks.append(("head", pts[max(k, 2) - 1]))
        elif age <= flight + 2:
            marks.append(("blast", (pts[-1], age - flight)))
    for lon, lat, mag in quakes:
        marks.append(("quake", (xy(lon, lat), mag)))
    for i, p in enumerate(iss[max(0, step - 31):step + 1]):
        marks.append(("iss", (xy(*p), i == min(step, 31))))
    return marks


def render_marks(d, marks, col, variant):
    for kind, m in marks:
        if kind == "arc":
            if variant == "A":   # dashed
                for i in range(0, len(m) - 1, 2):
                    if abs(m[i][0] - m[i + 1][0]) < MAP_W / 2:
                        d.line([m[i], m[i + 1]], fill=col, width=2)
            else:                # solid, a bit heavier
                for p, q in zip(m, m[1:]):
                    if abs(p[0] - q[0]) < MAP_W / 2:
                        d.line([p, q], fill=col, width=3)
        elif kind == "head":
            x, y = m
            d.polygon([(x, y - 6), (x + 6, y), (x, y + 6), (x - 6, y)], outline=col, fill=col)
        elif kind == "blast":
            (x, y), n = m
            for r in range(8, 8 + 10 * n + 1, 10):
                d.ellipse((x - r, y - r, x + r, y + r), outline=col, width=2)
        elif kind == "quake":
            (x, y), mag = m
            r = 2 + (mag - 2) ** 2 * 1.6
            d.ellipse((x - r, y - r, x + r, y + r), outline=col, width=1)
        elif kind == "iss":
            (x, y), last = m
            d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=col)
            if last:
                d.ellipse((x - 9, y - 9, x + 9, y + 9), outline=col, width=2)


def scene(variant, seed=4, steps=20):
    rnd = random.Random(seed)
    quakes = [(rnd.uniform(-180, 180), rnd.uniform(-50, 60), rnd.uniform(2.5, 5.5)) for _ in range(25)]
    quakes.append((142.0, 38.0, 6.3))
    iss = [(((-100 + 360 * i / 31) + 180) % 360 - 180, 51.6 * math.sin(2 * math.pi * i / 31)) for i in range(steps + 1)]
    msl = missiles(seed, steps)

    im = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(im)
    world = Image.open(REPO / "firmware/badge/data/earth/world.png")
    red = Image.new("RGB", world.size, WHITE)
    mask = Image.frombytes("L", world.size, bytes(255 if v == 2 else 0 for v in world.getdata()))
    red.paste(RED, mask=mask)
    im.paste(red, (0, MAP_Y))
    if variant == "B":   # dotted lat/lon grid every 30 degrees, black
        for lon in range(-180, 181, 30):
            x = int(xy(lon, 0)[0])
            for y in range(MAP_Y, MAP_Y + MAP_H, 6):
                d.point((min(x, W - 1), y), fill=BLACK)
        for lat in range(-60, 61, 30):
            y = int(xy(0, lat)[1])
            for x in range(0, W, 6):
                d.point((x, y), fill=BLACK)

    # ghosts: marks from earlier updates that aren't drawn any more, fading
    now = draw_frame(steps, msl, quakes, iss, variant)
    now_keys = {repr(m) for m in now}
    for back in range(8, 0, -1):
        g = 140 + back * 12
        old = [m for m in draw_frame(steps - back, msl, quakes, iss, variant) if repr(m) not in now_keys]
        render_marks(d, old, (g, g, g), variant)
    render_marks(d, now, BLACK, variant)

    quake_max = max(q[2] for q in quakes)
    defcon = 5 if quake_max < 4 else 4 if quake_max < 5 else 3 if quake_max < 6 else 2 if quake_max < 7 else 1
    flying = sum(1 for m in now if m[0] == "head")
    if variant == "A":
        big, small = ImageFont.truetype(DJ + "DejaVuSans-Bold.ttf", 26), ImageFont.truetype(DJ + "DejaVuSans.ttf", 15)
        d.text((10, 6), "LONG EXPOSURE EARTH", font=big, fill=BLACK)
        d.text((10, 40), "2026-11-07 21:15 UTC    ISS over the last orbit  +  earthquakes M2.5+, past 24 h  +  simulated missile tracks",
               font=small, fill=BLACK)
        d.text((10, 62), "DEFCON %d (set by the strongest quake: M%.1f)    %d tracks in flight    SIMULATION" % (defcon, quake_max, flying),
               font=small, fill=BLACK)
        y = MAP_Y + MAP_H + 8
        for line in ("Strongest quake: M6.3 off the coast of Honshu, Japan   (26 quakes)",
                     "ISS lat 12.4, lon -61.0   altitude 418 km   27580 km/h",
                     "Map: Natural Earth (naturalearthdata.com)   Data: wheretheiss.at, USGS"):
            d.text((10, y), line, font=small, fill=BLACK)
            y += 20
    else:
        mono_b, mono = ImageFont.truetype(DJ + "DejaVuSansMono-Bold.ttf", 26), ImageFont.truetype(DJ + "DejaVuSansMono.ttf", 15)
        d.text((10, 6), "STRATEGIC EXPOSURE // GLOBAL SIMULATION", font=mono_b, fill=BLACK)
        d.text((10, 42), "21:15Z  TRACKS IN FLIGHT: %02d   ISS: LAST ORBIT   SEISMIC: %d EVENTS M2.5+" % (flying, len(quakes)),
               font=mono, fill=BLACK)
        d.text((10, 64), "THIS IS A SIMULATION. NO REAL LAUNCHES ARE SHOWN.", font=mono, fill=BLACK)
        # DEFCON box, top right; the current level in red would need a full refresh
        bx = W - 220
        d.rectangle((bx, 8, W - 10, 84), outline=BLACK, width=3)
        d.text((bx + 14, 14), "DEFCON", font=mono_b, fill=BLACK)
        for i in range(5):
            x = bx + 14 + i * 38
            lvl = 5 - i
            box = (x, 50, x + 30, 78)
            if lvl == defcon:
                d.rectangle(box, fill=RED)
            else:
                d.rectangle(box, outline=BLACK, width=2)
            d.text((x + 8, 51), str(lvl), font=mono_b, fill=WHITE if lvl == defcon else BLACK)
        y = MAP_Y + MAP_H + 8
        for line in ("> STRONGEST EVENT: M6.3 OFF THE COAST OF HONSHU, JAPAN",
                     "> ISS 12.4N 61.0W  ALT 418 KM  27580 KM/H",
                     "> MAP: NATURAL EARTH (NATURALEARTHDATA.COM)  DATA: WHERETHEISS.AT, USGS"):
            d.text((10, y), line, font=mono, fill=BLACK)
            y += 20
    return im


def main():
    a, b = scene("A"), scene("B")
    sheet = Image.new("RGB", (W, H * 2 + 60), (60, 60, 60))
    lab = ImageFont.truetype(DJ + "DejaVuSans-Bold.ttf", 22)
    d = ImageDraw.Draw(sheet)
    d.text((10, 2), "A: overlay on today's layout", font=lab, fill=WHITE)
    sheet.paste(a, (0, 30))
    d.text((10, H + 32), "B: war room (grid, monospace, DEFCON box)", font=lab, fill=WHITE)
    sheet.paste(b, (0, H + 60))
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "earth_wopr.png")


if __name__ == "__main__":
    main()
