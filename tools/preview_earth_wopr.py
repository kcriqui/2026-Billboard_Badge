#!/usr/bin/env python3
"""Preview layouts for the WOPR app (Long Exposure Earth, war-room style).

    python3 tools/preview_earth_wopr.py out.png

Two boards, both 960x672 in the panel's white/black/red, after an hour of
3-minute updates; marks no longer drawn are shown as fading grey ghosts,
roughly how the panel's fast refresh leaves them:
  W  world board: equirectangular map, dashed missile arcs (like the
     film's big world screen), banner lettering, track labels
  P  polar board: map centred on the North Pole with rings and spokes,
     tracks as bundles of parallel streaks over the pole, side panels
Style notes from the film's war-room frames (hp9845.net WarGames gallery):
thin vector lettering, numbered track labels, status-code lines, red for
one side. Map: Natural Earth land (tools/data/ne_110m_land.geojson).
Needs Pillow.
"""

import json
import math
import pathlib
import random
import sys

from PIL import Image, ImageDraw, ImageFont

REPO = pathlib.Path(__file__).resolve().parent.parent
W, H = 960, 672
TOP = 96                      # map area starts here
RED, BLACK, WHITE = (205, 25, 30), (0, 0, 0), (255, 255, 255)
DJ = "/usr/share/fonts/truetype/dejavu/"
LAND = json.load(open(REPO / "tools/data/ne_110m_land.geojson"))["features"]

CITIES = {
    "SEATTLE": (-122.3, 47.6), "DENVER": (-105.0, 39.7), "CHICAGO": (-87.6, 41.9),
    "NEW YORK": (-74.0, 40.7), "LOS ANGELES": (-118.2, 34.1), "ANCHORAGE": (-149.9, 61.2),
    "LONDON": (-0.1, 51.5), "PARIS": (2.4, 48.9), "HONOLULU": (-157.9, 21.3),
    "MOSCOW": (37.6, 55.8), "MURMANSK": (33.1, 69.0), "NOVOSIBIRSK": (82.9, 55.0),
    "VLADIVOSTOK": (131.9, 43.1), "BEIJING": (116.4, 39.9), "BERLIN": (13.4, 52.5),
}
SIDES = (["SEATTLE", "DENVER", "CHICAGO", "NEW YORK", "LOS ANGELES", "ANCHORAGE",
          "LONDON", "PARIS", "HONOLULU"],
         ["MOSCOW", "MURMANSK", "NOVOSIBIRSK", "VLADIVOSTOK", "BEIJING", "BERLIN"])


def font(name, size):
    return ImageFont.truetype(DJ + name, size)


MONO, MONO_B = font("DejaVuSansMono.ttf", 15), font("DejaVuSansMono-Bold.ttf", 26)
THIN = font("DejaVuSans-ExtraLight.ttf", 44)  # stand-in for vector lettering


# ---- projections ---------------------------------------------------------

class World:
    name = "W"
    def xy(self, lon, lat):
        return (lon + 180) * W / 360, TOP + (90 - lat) * 480 / 180
    def visible(self, lon, lat):
        return True


class Polar:
    """Azimuthal equidistant around the North Pole, down to MIN_LAT at the
    rim; North America at the bottom, Russia at the top."""
    name = "P"
    CX, CY, R, MIN_LAT, LON0 = 480, TOP + 240, 238, -20, -100
    def xy(self, lon, lat):
        r = (90 - lat) / (90 - self.MIN_LAT) * self.R
        t = math.radians(lon - self.LON0)
        return self.CX + r * math.sin(t), self.CY + r * math.cos(t)
    def visible(self, lon, lat):
        return lat >= self.MIN_LAT


def draw_land(d, proj):
    for f in LAND:
        ring = f["geometry"]["coordinates"][0]
        for (a, b), (c, e) in zip(ring, ring[1:]):
            if proj.visible(a, b) and proj.visible(c, e):
                p, q = proj.xy(a, b), proj.xy(c, e)
                if abs(p[0] - q[0]) < W / 2:
                    d.line([p, q], fill=RED, width=2)


def draw_polar_grid(d, p):
    for lat in (60, 30, 0):
        r = (90 - lat) / (90 - p.MIN_LAT) * p.R
        for k in range(0, 360, 2):  # dotted ring
            t = math.radians(k)
            d.point((p.CX + r * math.sin(t), p.CY + r * math.cos(t)), fill=BLACK)
    d.ellipse((p.CX - p.R, p.CY - p.R, p.CX + p.R, p.CY + p.R), outline=BLACK, width=2)
    for lon in range(-180, 180, 30):
        x, y = p.xy(lon, p.MIN_LAT)
        n = 60
        for i in range(0, n, 2):  # dotted spoke
            d.point((p.CX + (x - p.CX) * i / n, p.CY + (y - p.CY) * i / n), fill=BLACK)


# ---- made-up missiles ------------------------------------------------------

def missiles(seed, steps):
    rnd = random.Random(seed)
    out = []
    for s in range(0, steps, 3):
        for _ in range(rnd.choice((1, 2, 2, 3))):
            side = rnd.randrange(2)
            out.append(dict(launch=s + rnd.randrange(3), flight=rnd.randrange(7, 12),
                            a=rnd.choice(SIDES[side]), b=rnd.choice(SIDES[1 - side]),
                            id=rnd.randrange(1000, 9999)))
    return out


def track(m, proj, n=48):
    """World: ballistic-looking arc bulging north. Polar: near-straight
    track over the pole (a great circle there looks almost straight)."""
    (lo0, la0), (lo2, la2) = m_pos(m["a"]), m_pos(m["b"])
    if proj.name == "P":
        return [proj.xy(*great_circle(lo0, la0, lo2, la2, i / n)) for i in range(n + 1)]
    (x0, y0), (x2, y2) = proj.xy(lo0, la0), proj.xy(lo2, la2)
    if abs(x2 - x0) > W / 2:
        x2 += -W if x2 > x0 else W
    dd = math.hypot(x2 - x0, y2 - y0)
    cx, cy = (x0 + x2) / 2, max(min(y0, y2) - dd / 4, TOP + 30)
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append((((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x2) % W,
                    (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y2))
    return pts


def m_pos(city):
    return CITIES[city]


def great_circle(lo1, la1, lo2, la2, f):
    p1, l1, p2, l2 = map(math.radians, (la1, lo1, la2, lo2))
    v1 = (math.cos(p1) * math.cos(l1), math.cos(p1) * math.sin(l1), math.sin(p1))
    v2 = (math.cos(p2) * math.cos(l2), math.cos(p2) * math.sin(l2), math.sin(p2))
    om = math.acos(max(-1, min(1, sum(a * b for a, b in zip(v1, v2)))))
    a, b = math.sin((1 - f) * om) / math.sin(om), math.sin(f * om) / math.sin(om)
    v = [a * x + b * y for x, y in zip(v1, v2)]
    return math.degrees(math.atan2(v[1], v[0])), math.degrees(math.asin(v[2]))


def frame(step, msl, proj, quakes, iss):
    marks = []
    for m in msl:
        age = step - m["launch"]
        if age < 0:
            continue
        pts = track(m, proj)
        if age <= m["flight"]:
            k = max(2, int(len(pts) * age / m["flight"]))
            marks.append(("trk", tuple(pts[:k])))
            marks.append(("head", (pts[k - 1], m["id"], m["a"] in SIDES[0])))
            marks.append(("label", (pts[0], m["id"])))
            if age == 0 or age == 1:
                marks.append(("launch", pts[0]))
        elif age <= m["flight"] + 2:
            marks.append(("blast", (pts[-1], age - m["flight"])))
    for lon, lat, mag in quakes:
        if proj.visible(lon, lat):
            marks.append(("quake", (proj.xy(lon, lat), mag)))
    for i, (lon, lat) in enumerate(iss[max(0, step - 31):step + 1]):
        if proj.visible(lon, lat):
            marks.append(("iss", (proj.xy(lon, lat), i == min(step, 31))))
    return marks


def render(d, marks, col, proj):
    for kind, m in marks:
        if kind == "trk":
            if proj.name == "W":       # dashes, like the film's world screen
                for i in range(0, len(m) - 1, 2):
                    if abs(m[i][0] - m[i + 1][0]) < W / 2:
                        d.line([m[i], m[i + 1]], fill=col, width=2)
            else:                      # bundle of three parallel streaks
                (x0, y0), (x1, y1) = m[0], m[-1]
                L = math.hypot(x1 - x0, y1 - y0) or 1
                nx, ny = -(y1 - y0) / L, (x1 - x0) / L
                for off in (-5, 0, 5):
                    d.line([(x + nx * off, y + ny * off) for x, y in m], fill=col, width=2)
        elif kind == "head":
            (x, y), tid, west = m
            d.polygon([(x, y - 6), (x + 6, y), (x, y + 6), (x - 6, y)], fill=col)
        elif kind == "label":   # at the launch point: doesn't move, no smear
            (x, y), tid = m
            d.text((x + 6, y + 4), "%d" % tid, font=MONO, fill=col)
        elif kind == "launch":
            x, y = m
            d.ellipse((x - 12, y - 12, x + 12, y + 12), outline=col, width=2)
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


def defcon_box(d, x, y, level):
    d.rectangle((x, y, x + 210, y + 76), outline=BLACK, width=3)
    d.text((x + 14, y + 4), "DEFCON", font=MONO_B, fill=BLACK)
    for i in range(5):
        lvl, bx = 5 - i, x + 14 + i * 38
        if lvl == level:
            d.rectangle((bx, y + 42, bx + 30, y + 70), fill=RED)
        else:
            d.rectangle((bx, y + 42, bx + 30, y + 70), outline=BLACK, width=2)
        d.text((bx + 8, y + 41), str(lvl), font=MONO_B, fill=WHITE if lvl == level else BLACK)


def board(proj, seed=4, steps=20):
    rnd = random.Random(seed)
    quakes = [(rnd.uniform(-180, 180), rnd.uniform(-50, 60), rnd.uniform(2.5, 5.5)) for _ in range(25)]
    quakes.append((142.0, 38.0, 6.3))
    iss = [(((-100 + 360 * i / 31) + 180) % 360 - 180, 51.6 * math.sin(2 * math.pi * i / 31))
           for i in range(steps + 1)]
    msl = missiles(seed, steps)
    im = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(im)
    if proj.name == "P":
        draw_polar_grid(d, proj)
    draw_land(d, proj)
    now = frame(steps, msl, proj, quakes, iss)
    keys = {repr(m) for m in now}
    for back in range(8, 0, -1):
        g = 140 + back * 12
        render(d, [m for m in frame(steps - back, msl, proj, quakes, iss) if repr(m) not in keys], (g, g, g), proj)
    render(d, now, BLACK, proj)

    flying = sum(1 for m in now if m[0] == "head")
    launched = any(m[0] == "launch" for m in now)
    banner = "LAUNCH DETECTION" if launched else "MISSILE WARNING" if flying else "NO TRACKS"
    defcon = 2
    d.text((10, 6), "WOPR", font=MONO_B, fill=BLACK)
    d.text((100, 6), "// STRATEGIC DISPLAY", font=MONO_B, fill=BLACK)
    d.text((10, 42), "21:15Z  TRACKS: %02d   ISS: TRACKING   SEISMIC: 26 EVENTS M2.5+" % flying, font=MONO, fill=BLACK)
    d.text((10, 64), "STS DSP 2 GRID REF: 4120/0610   LOC RF: NORAD", font=MONO, fill=BLACK)
    defcon_box(d, W - 220, 8, defcon)
    foot = ["> STRONGEST EVENT: M6.3 OFF THE COAST OF HONSHU, JAPAN",
            "> ISS 12.4N 61.0W  ALT 418 KM  27580 KM/H",
            "> MAP: NATURAL EARTH (NATURALEARTHDATA.COM)  DATA: WHERETHEISS.AT, USGS"]
    if proj.name == "W":
        d.text((24, TOP + 330), banner, font=THIN, fill=BLACK)
        for i, line in enumerate(foot):
            d.text((10, TOP + 488 + i * 20), line, font=MONO, fill=BLACK)
    else:
        d.text((24, TOP + 6), banner.split()[0], font=THIN, fill=BLACK)
        d.text((24, TOP + 52), " ".join(banner.split()[1:]), font=THIN, fill=BLACK)
        y = TOP + 130
        d.text((10, y), "TRK   ORIGIN > TGT", font=MONO, fill=BLACK)
        for kind, m in now:
            if kind == "head":
                y += 20
                d.text((10, y), "%d  %s" % (m[1], "WEST" if m[2] else "EAST"), font=MONO, fill=BLACK)
        for i, line in enumerate(["ISS 12.4N 61.0W", "ALT 418 KM", "", "M6.3 HONSHU", "26 EVENTS M2.5+"]):
            d.text((W - 210, TOP + 130 + i * 20), line, font=MONO, fill=BLACK)
        d.text((10, H - 22), "MAP: NATURAL EARTH  DATA: WHERETHEISS.AT, USGS", font=MONO, fill=BLACK)
    return im


def main():
    a, b = board(World()), board(Polar())
    sheet = Image.new("RGB", (W, H * 2 + 60), (60, 60, 60))
    d = ImageDraw.Draw(sheet)
    lab = font("DejaVuSans-Bold.ttf", 22)
    d.text((10, 2), "W: world board (dashed arcs, banner)", font=lab, fill=WHITE)
    sheet.paste(a, (0, 30))
    d.text((10, H + 32), "P: polar board (rings and spokes, streak bundles over the pole)", font=lab, fill=WHITE)
    sheet.paste(b, (0, H + 60))
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "wopr.png")


if __name__ == "__main__":
    main()
