"""Long Exposure Earth, war-room edition: ISS, earthquakes and simulated
missile tracks on a red world map, in the style of a 1980s strategic
display (an homage to the film WarGames; Kevin's option B, 2026-11-07).

Every UPDATE_S the ISS position is added; only the last orbit is drawn in
black, so older positions fade out as e-paper ghosts left by the fast
refresh (keep_red=True leaves the red map untouched). Earthquakes (USGS,
M2.5+ in the past day) are refreshed every QUAKE_S and drawn as rings sized
by magnitude.

Simulated missiles (made up, nothing real): salvos between cities on two
fictional sides. Each track grows a step per update behind a diamond head,
lands with blast rings, then stops being drawn and fades as a ghost - the
long exposure again. DEFCON comes from real data: the strongest quake of
the past day (M<4 -> 5 ... M7+ -> 1); its red box changes only with a full
refresh, so a new level triggers one.

A full refresh - the flash - wipes the ghosts on launch, every FULL_S, when
a new M6+ quake appears and when DEFCON changes.

User A: update now. User B: full refresh now (wipe the ghosts).

Data: ISS position from wheretheiss.at; earthquakes from the USGS
Earthquake Hazards Program feed.
Map: Made with Natural Earth. Free vector and raster map data @
naturalearthdata.com (data/earth/world.png, made by tools/make_world_map.py).
Layout previews: tools/preview_earth_wopr.py.
"""

import array
import gc
import json
import random
import time

from apps.base_app import BaseApp
from lib import bitfont, font_mono, font_mono_big, net, wifi
from lib.button import UserA, UserB
from lib.epd import display, display_height, display_width
from lib.led_bar import leds

UPDATE_S = 3 * 60
QUAKE_S = 15 * 60
FULL_S = 60 * 60
RETRY_S = 60
TRAIL = 31            # ISS dots drawn in black: ~1 orbit at 3-minute steps
BIG_QUAKE = 6.0       # a new quake this strong triggers a full refresh

ISS_URL = "https://api.wheretheiss.at/v1/satellites/25544"
QUAKE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
MAP_PATH = "/data/earth/world.png"
MAP_Y, MAP_W, MAP_H = 96, 960, 480
ROW_BYTES = display_width // 8
UNIX_TO_MP_EPOCH = 946684800  # MicroPython's time counts from 2000-01-01

# Simulated missiles
SALVO_EVERY = 3       # updates between salvos
SALVO_SIZES = (1, 2, 2, 3)
FLIGHT = (7, 12)      # updates per flight: ~20-35 min
BLAST_STEPS = 2       # updates the blast rings stay after landing
ARC_POINTS = 48
GRID_DEG = 30

# Launch sites / targets are just cities (lon, lat); two fictional sides.
CITIES = {
    "SEATTLE": (-122.3, 47.6), "DENVER": (-105.0, 39.7), "CHICAGO": (-87.6, 41.9),
    "NEW YORK": (-74.0, 40.7), "LOS ANGELES": (-118.2, 34.1), "ANCHORAGE": (-149.9, 61.2),
    "LONDON": (-0.1, 51.5), "PARIS": (2.4, 48.9), "HONOLULU": (-157.9, 21.3),
    "MOSCOW": (37.6, 55.8), "MURMANSK": (33.1, 69.0), "NOVOSIBIRSK": (82.9, 55.0),
    "VLADIVOSTOK": (131.9, 43.1), "BEIJING": (116.4, 39.9), "BERLIN": (13.4, 52.5),
}
SIDES = (("SEATTLE", "DENVER", "CHICAGO", "NEW YORK", "LOS ANGELES", "ANCHORAGE",
          "LONDON", "PARIS", "HONOLULU"),
         ("MOSCOW", "MURMANSK", "NOVOSIBIRSK", "VLADIVOSTOK", "BEIJING", "BERLIN"))


def _xy(lon, lat):
    return int((lon + 180) * MAP_W / 360), MAP_Y + int((90 - lat) * MAP_H / 180)


def _mark(x, y, r, fill=False):
    """Black circle; clears red under it (black + red = an undriven pixel)."""
    display.black.ellipse(x, y, r, r, 1, fill)
    display.red.ellipse(x, y, r, r, 0, fill)


def _line(x0, y0, x1, y1):
    """3 px black line, red cleared under it."""
    for d in (-1, 0, 1):
        display.black.line(x0, y0 + d, x1, y1 + d, 1)
        display.red.line(x0, y0 + d, x1, y1 + d, 0)


_DIAMOND = array.array("h", (0, -6, 6, 0, 0, 6, -6, 0))


def _diamond(x, y):
    display.black.poly(x, y, _DIAMOND, 1, True)
    display.red.poly(x, y, _DIAMOND, 0, True)


def _arc(a, b):
    """Ballistic-looking track from city a to b: a quadratic curve bulging
    north by a quarter of its length; the short way across the date line."""
    lon0, lat0 = CITIES[a]
    lon2, lat2 = CITIES[b]
    x0 = (lon0 + 180) * MAP_W / 360
    x2 = (lon2 + 180) * MAP_W / 360
    y0 = MAP_Y + (90 - lat0) * MAP_H / 180
    y2 = MAP_Y + (90 - lat2) * MAP_H / 180
    if abs(x2 - x0) > MAP_W / 2:
        x2 += -MAP_W if x2 > x0 else MAP_W
    d = ((x2 - x0) ** 2 + (y2 - y0) ** 2) ** 0.5
    cx = (x0 + x2) / 2
    cy = max(min(y0, y2) - d / 4, MAP_Y + 30)
    pts = []
    for i in range(ARC_POINTS + 1):
        t = i / ARC_POINTS
        u = 1 - t
        x = u * u * x0 + 2 * u * t * cx + t * t * x2
        y = u * u * y0 + 2 * u * t * cy + t * t * y2
        pts.append((int(x) % MAP_W, int(y)))
    return pts


def _defcon(quakes):
    mag = 0
    for q in quakes:
        mag = max(mag, q[2])
    return 5 if mag < 4 else 4 if mag < 5 else 3 if mag < 6 else 2 if mag < 7 else 1


def _clear_text(font, plane, x, y, text):
    """Draw text by clearing bits (white text on a filled red box)."""
    pen = x << 4
    for ch in bitfont._clean(text):
        i = ord(ch) - font.FIRST
        w, off, rb = font.WIDTHS[i], font.OFFSETS[i], (font.WIDTHS[i] + 7) >> 3
        gx = (pen + 8) >> 4
        for r in range(font.HEIGHT):
            row = off + r * rb
            for c in range(w):
                if font.DATA[row + (c >> 3)] & (128 >> (c & 7)):
                    plane.pixel(gx + c, y + r, 0)
        pen += font.ADV16[i]


class EarthApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        super().__init__("Earth")
        self.sleep_ms = 100
        self.next_update = 0
        self.next_quakes = 0
        self.last_full = -FULL_S
        self.trail = []
        self.quakes = []
        self.seen_big = set()
        self.iss = None
        self._map = None
        self.step = 0
        self.missiles = []     # [launch_step, flight_steps, arc points]
        self.defcon = None     # level shown at the last full refresh

    # ---- data ---------------------------------------------------------------

    def _fetch(self):
        wifi.connect()
        self.iss = json.loads(bytes(net.https_get(ISS_URL, 4096)))
        self.trail.append((self.iss["longitude"], self.iss["latitude"]))
        self.trail = self.trail[-TRAIL:]
        new_big = False
        if time.time() >= self.next_quakes:
            feed = json.loads(bytes(net.https_get(QUAKE_URL, 256 * 1024)))
            baseline = self.next_quakes == 0  # first load: nothing is "new"
            self.quakes = []
            for f in feed["features"]:
                lon, lat = f["geometry"]["coordinates"][:2]
                p = f["properties"]
                mag = p["mag"] or 0
                self.quakes.append((lon, lat, mag, p.get("place") or ""))
                if mag >= BIG_QUAKE and f["id"] not in self.seen_big:
                    new_big = new_big or not baseline
                    self.seen_big.add(f["id"])
            feed = None
            self.next_quakes = time.time() + QUAKE_S
            gc.collect()
        return new_big

    def _simulate(self):
        """Advance the made-up missiles one update: launch salvos, drop
        tracks whose blast rings have had their time."""
        self.step += 1
        if self.step % SALVO_EVERY == 1:
            for _ in range(random.choice(SALVO_SIZES)):
                side = random.getrandbits(1)
                a = random.choice(SIDES[side])
                b = random.choice(SIDES[1 - side])
                flight = FLIGHT[0] + random.getrandbits(8) % (FLIGHT[1] - FLIGHT[0] + 1)
                self.missiles.append([self.step + random.getrandbits(8) % SALVO_EVERY, flight, _arc(a, b)])
        self.missiles = [m for m in self.missiles if self.step - m[0] <= m[1] + BLAST_STEPS]

    # ---- drawing --------------------------------------------------------------

    def _draw_map(self):
        """Map planes from cache (decoding the PNG takes seconds), with the
        dotted lat/lon grid baked in."""
        start, end = MAP_Y * ROW_BYTES, (MAP_Y + MAP_H) * ROW_BYTES
        if self._map is None:
            display.clear()
            display.draw_png(MAP_PATH, row=MAP_Y, col=0)
            black, red = display.black, display.red
            for lon in range(-180, 181, GRID_DEG):
                x = min(_xy(lon, 0)[0], display_width - 1)
                for y in range(MAP_Y, MAP_Y + MAP_H, 6):
                    black.pixel(x, y, 1)
                    red.pixel(x, y, 0)
            for lat in range(-60, 61, GRID_DEG):
                y = _xy(0, lat)[1]
                for x in range(0, display_width, 6):
                    black.pixel(x, y, 1)
                    red.pixel(x, y, 0)
            self._map = (bytes(display._framebuffer_black[start:end]),
                         bytes(display._framebuffer_red[start:end]))
        display.clear()
        display._framebuffer_black[start:end] = self._map[0]
        display._framebuffer_red[start:end] = self._map[1]

    def _draw_missiles(self):
        flying = 0
        for launch, flight, pts in self.missiles:
            age = self.step - launch
            if age < 0:
                continue
            if age <= flight:
                k = max(2, len(pts) * age // flight)
                for (x0, y0), (x1, y1) in zip(pts[:k - 1], pts[1:k]):
                    if abs(x1 - x0) < MAP_W // 2:  # skip the date-line jump
                        _line(x0, y0, x1, y1)
                _diamond(*pts[k - 1])
                flying += 1
            else:
                x, y = pts[-1]
                for r in range(8, 8 + 10 * (age - flight) + 1, 10):
                    _mark(x, y, r)
                    _mark(x, y, r + 1)
        return flying

    def _draw_data(self):
        for lon, lat, mag, _ in self.quakes:
            x, y = _xy(lon, lat)
            r = int(2 + (mag - 2) ** 2 * 1.6)
            _mark(x, y, r)
            if mag >= BIG_QUAKE:
                _mark(x, y, r + 6)
        for lon, lat in self.trail:
            x, y = _xy(lon, lat)
            _mark(x, y, 3, True)
        if self.trail:
            x, y = _xy(*self.trail[-1])
            _mark(x, y, 9)
            _mark(x, y, 8)
        return self._draw_missiles()

    def _draw_defcon(self, level):
        """DEFCON box, top right; the current level is a red box with a
        white digit (red only changes with a full refresh)."""
        black, red = display.black, display.red
        bx = display_width - 220
        for i in range(3):
            black.rect(bx + i, 8 + i, 210 - 2 * i, 78 - 2 * i, 1)
        bitfont.draw(font_mono_big, display._framebuffer_black, bx + 14, 10, "DEFCON")
        for i in range(5):
            lvl = 5 - i
            x = bx + 14 + i * 38
            if lvl == level:
                red.fill_rect(x, 50, 31, 30, 1)
                _clear_text(font_mono_big, red, x + 8, 49, str(lvl))
            else:
                black.rect(x, 50, 31, 30, 1)
                black.rect(x + 1, 51, 29, 28, 1)
                bitfont.draw(font_mono_big, display._framebuffer_black, x + 8, 49, str(lvl))

    def _draw_text(self, flying, level):
        """Header and footer in 1-bit monospace bitmap fonts (lib/bitfont),
        straight into the black plane; those bands hold no red except the
        DEFCON box."""
        black = display._framebuffer_black
        t = time.gmtime(self.iss["timestamp"] - UNIX_TO_MP_EPOCH)
        bitfont.draw(font_mono_big, black, 10, 6, "STRATEGIC EXPOSURE // GLOBAL SIMULATION")
        bitfont.draw(font_mono, black, 10, 42,
                     "%02d:%02dZ  TRACKS IN FLIGHT: %02d   ISS: LAST ORBIT   SEISMIC: %d EVENTS M2.5+"
                     % (t[3], t[4], flying, len(self.quakes)))
        bitfont.draw(font_mono, black, 10, 64, "THIS IS A SIMULATION. NO REAL LAUNCHES ARE SHOWN.")
        self._draw_defcon(level)
        lines = []
        if self.quakes:
            big = max(self.quakes, key=lambda q: q[2])
            lines.append("> STRONGEST EVENT: M%.1f %s" % (big[2], big[3].upper()))
        lat, lon = self.iss["latitude"], self.iss["longitude"]
        lines.append("> ISS %.1f%s %.1f%s  ALT %.0f KM  %.0f KM/H" % (
            abs(lat), "N" if lat >= 0 else "S", abs(lon), "E" if lon >= 0 else "W",
            self.iss["altitude"], self.iss["velocity"]))
        lines.append("> MAP: NATURAL EARTH (NATURALEARTHDATA.COM)  DATA: WHERETHEISS.AT, USGS")
        bitfont.draw_lines(font_mono, black, lines, 10, MAP_Y + MAP_H + 8,
                           display_width - 20, max_lines=3)

    # ---- app loop -------------------------------------------------------------

    def _update(self, force_full=False):
        if not display.is_done_updating():
            self.next_update = time.time() + 5
            return
        leds.fill((0, 0, 2))
        leds.write()
        try:
            new_big = self._fetch()
        except Exception as ex:  # network hiccup: keep the old picture
            print("earth: update failed:", repr(ex))
            leds.fill((2, 0, 0))
            leds.write()
            self.next_update = time.time() + RETRY_S
            return
        leds.fill((0, 0, 0))
        leds.write()
        if self.step == 0:  # start mid-exchange, not with an empty board
            for _ in range(9):
                self._simulate()
        self._simulate()
        level = _defcon(self.quakes)
        full = (force_full or self.launched or new_big or level != self.defcon
                or time.time() - self.last_full >= FULL_S)
        if full:
            self.last_full = time.time()
            self.defcon = level
        self._draw_map()
        flying = self._draw_data()
        self._draw_text(flying, self.defcon)
        print("earth: ISS %.1f %.1f, %d quakes, %d tracks, DEFCON %d, %s refresh%s" % (
            self.iss["latitude"], self.iss["longitude"], len(self.quakes), flying,
            self.defcon, "full" if full else "fast", " (new M6+ quake)" if new_big else ""))
        display.update(fast=not full, keep_red=not full)
        self.next_update = time.time() + UPDATE_S
        gc.collect()

    def run(self):
        if self.launched or time.time() >= self.next_update:
            self._update()
        elif UserA.pressed():
            self._update()
        elif UserB.pressed():
            self._update(force_full=True)
