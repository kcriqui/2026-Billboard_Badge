"""WOPR: a war-room strategic display (an homage to the film WarGames) built
on Long Exposure Earth: the ISS, earthquakes and made-up missile tracks,
on two boards that alternate every VIEW_S:

  WORLD  equirectangular map, dashed ballistic arcs, a big banner
  POLAR  map centred on the North Pole with rings and spokes, tracks as
         bundles of streaks over the pole, track list and data panels

Style taken from the film's war-room screens (vector lettering, numbered
tracks, status-code lines, DEFCON board; reference frames on hp9845.net).
Kevin picked both boards from tools/preview_earth_wopr.py, 2026-11-07.

Missiles are made up (cities on two fictional sides). They are stored as
city-to-city flights with launch times, independent of the map, so tracks
carry on across a view change; each view draws them in its own projection.
A track grows a step per update, lands with a mushroom cloud, then stops being
drawn and fades as an e-paper ghost - the long exposure. Now and then
(BIG_SALVO_ODDS) a big salvo heads for US cities.

DEFCON = missiles in flight toward US cities (0 -> 5 ... 6+ -> 1). Its red
box only changes with a full refresh: a rising alert gets one at once, a
falling one waits for the next scheduled full refresh.

Every UPDATE_S the ISS position is added (last orbit drawn); quakes (USGS
M2.5+, past day) every QUAKE_S.

Refresh: fast with keep_red (red map untouched) between full refreshes; full
on launch, view change, rising DEFCON, a new M6+ quake, and every FULL_S.
User A: switch to the other board now (fresh data, full refresh).
User B: launch a big salvo at US cities now (DEFCON goes up).

When a salvo at the US has landed (both mushroom-cloud stages shown), the
board clears (no tracks) and WOPR shows the lesson it learned in the film,
black on white over the map, with the quick refresh (Kevin, 2026-11-07).
It stays until the next update; DEFCON falls back at the next full refresh.

Data: ISS position from wheretheiss.at; earthquakes from the USGS
Earthquake Hazards Program feed.
Maps: Made with Natural Earth. Free vector and raster map data @
naturalearthdata.com (data/earth/world.png and polar.png, made by
tools/make_world_map.py).
"""

import array
import gc
import json
import math
import random
import time

import micropython

from apps.base_app import BaseApp
import framebuf

from lib import bitfont, font_mono, font_mono_big, font_mono_huge, font_thin, net, wifi
from lib import sprite_mushroom
from lib.button import UserA, UserB
from lib.epd import display, display_height, display_width
from lib.led_bar import leds

UPDATE_S = 3 * 60
VIEW_S = 10 * 60       # switch boards this often (Kevin, 2026-11-07)
QUAKE_S = 15 * 60
FULL_S = 60 * 60
RETRY_S = 60
TRAIL = 31             # ISS dots drawn: ~1 orbit at 3-minute steps
BIG_QUAKE = 6.0        # a new quake this strong triggers a full refresh

ISS_URL = "https://api.wheretheiss.at/v1/satellites/25544"
QUAKE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
MAP_Y, MAP_W, MAP_H = 96, 960, 480
ROW_BYTES = display_width // 8
PLANE_BYTES = ROW_BYTES * display_height
UNIX_TO_MP_EPOCH = 946684800  # MicroPython's time counts from 2000-01-01

# Polar board: must match tools/make_world_map.py POLAR_* (map image coords)
POLAR_CX, POLAR_CY, POLAR_R, POLAR_MIN_LAT, POLAR_LON0 = 480, 240, 238, -20, -100

# Made-up missiles
SALVO_EVERY = 3        # updates between salvos
SALVO_SIZES = (1, 2, 2, 3)
BIG_SALVO_ODDS = 10    # 1 salvo in this many is a big one at US cities (~every 1.5 h)
BIG_SALVO = (4, 8)     # missiles in a big salvo: DEFCON 2 or 1
FLIGHT = (7, 12)       # updates per flight: ~20-35 min
BLAST_STEPS = 2        # updates the mushroom cloud stays after landing (young, full)
TRACK_POINTS = 48
LIFT = (0.50, 0.80)    # arc height range (fraction of track length), per missile;
                       # higher arcs, same flight time (Kevin, 2026-11-07)
PREROLL = 9            # start mid-exchange, not with an empty board
LESSON_X = 148         # left edge of the lesson text block (centres the longest line)

# Launch sites / targets are just cities (lon, lat) on three made-up sides.
CITIES = {
    "SEATTLE": (-122.3, 47.6), "DENVER": (-105.0, 39.7), "CHICAGO": (-87.6, 41.9),
    "NEW YORK": (-74.0, 40.7), "LOS ANGELES": (-118.2, 34.1), "ANCHORAGE": (-149.9, 61.2),
    "LONDON": (-0.1, 51.5), "PARIS": (2.4, 48.9), "HONOLULU": (-157.9, 21.3),
    "MOSCOW": (37.6, 55.8), "MURMANSK": (33.1, 69.0), "NOVOSIBIRSK": (82.9, 55.0),
    "VLADIVOSTOK": (131.9, 43.1), "BEIJING": (116.4, 39.9), "BERLIN": (13.4, 52.5),
    # third side (Kevin, 2026-11-07): South Africa, Venezuela, Australia
    "JOHANNESBURG": (28.0, -26.2), "CARACAS": (-66.9, 10.5), "SYDNEY": (151.2, -33.9),
    # southern-hemisphere targets only
    "SAO PAULO": (-46.6, -23.5), "BUENOS AIRES": (-58.4, -34.6), "LIMA": (-77.0, -12.0),
    "CAPE TOWN": (18.4, -33.9), "PERTH": (115.9, -31.95), "AUCKLAND": (174.8, -36.8),
}
SIDE_NAMES = ("WEST", "EAST", "SOUTH")
SIDES = (("SEATTLE", "DENVER", "CHICAGO", "NEW YORK", "LOS ANGELES", "ANCHORAGE",
          "LONDON", "PARIS", "HONOLULU"),
         ("MOSCOW", "MURMANSK", "NOVOSIBIRSK", "VLADIVOSTOK", "BEIJING", "BERLIN"),
         ("JOHANNESBURG", "CARACAS", "SYDNEY"))
SOUTH_TARGETS = ("SAO PAULO", "BUENOS AIRES", "LIMA", "CAPE TOWN", "PERTH", "AUCKLAND")
USA = ("SEATTLE", "DENVER", "CHICAGO", "NEW YORK", "LOS ANGELES", "ANCHORAGE", "HONOLULU")
# Ordinary exchanges: any city not on the attacker's side, but never US
# cities, so DEFCON sits at 5 until a big salvo comes in.
TARGETS = tuple(tuple(c for i, side in enumerate(SIDES) if i != a for c in side if c not in USA)
                + SOUTH_TARGETS for a in range(len(SIDES)))


def _side_name(city):
    for i, side in enumerate(SIDES):
        if city in side:
            return SIDE_NAMES[i]
    return "?"


CLOSE_STEPS = 2        # a US-bound missile this many updates from impact is "close"
CLOSE_FOR_1 = 3        # DEFCON 1 only when at least this many are close
PATH_GAP = 10          # px between the dots of the faint path to the target
DOT = 2                # dot size: single pixels didn't darken in a fast refresh
TARGET_R = 11          # faint dotted circle round each target


def _defcon(incoming, close):
    """DEFCON from missiles in flight toward US cities; 1 only when several
    of them are close to impact (Kevin, 2026-11-07)."""
    if close >= CLOSE_FOR_1:
        return 1
    return 5 if incoming == 0 else 4 if incoming == 1 else 3 if incoming <= 3 else 2


def _dotted(fb, pts, gap):
    """DOT x DOT dots every `gap` px along a polyline (a faint line on
    e-paper; lone single pixels stayed pale grey in a fast refresh, Kevin
    2026-11-07); skips the date-line jump on the world board."""
    carry = 0.0
    for p0, p1 in zip(pts, pts[1:]):
        if not (p0 and p1):         # beyond the polar board's rim
            carry = 0.0
            continue
        (x0, y0), (x1, y1) = p0, p1
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) > MAP_W // 2:
            continue
        seg = (dx * dx + dy * dy) ** 0.5
        d = carry
        while d < seg:
            f = d / seg
            fb.fill_rect(int(x0 + dx * f), int(y0 + dy * f), DOT, DOT, 1)
            d += gap
        carry = d - seg


def _dotted_circle(fb, x, y, r):
    for k in range(0, 360, 30):
        a = math.radians(k)
        fb.fill_rect(x + int(r * math.cos(a)), y + int(r * math.sin(a)), DOT, DOT, 1)


# ---- the two boards -----------------------------------------------------------

class World:
    number = 1
    map_path = "/data/earth/world.png"

    @staticmethod
    def xy(lon, lat):
        return int((lon + 180) * MAP_W / 360), MAP_Y + int((90 - lat) * MAP_H / 180)

    @staticmethod
    def visible(lat):
        return True

    @staticmethod
    def track(a, b, lift):
        """Ballistic-looking arc, high like the film's world screen: the
        peak sits `lift` (LIFT) of the east-west distance beyond the higher
        end - north, or south when the ends average south of the equator.
        Peaks that would leave the map are squeezed into a band near the
        edge, still spread by `lift`, so long arcs don't stack up there.
        The short way across the date line."""
        lon0, lat0 = CITIES[a]
        lon2, lat2 = CITIES[b]
        x0 = (lon0 + 180) * MAP_W / 360
        x2 = (lon2 + 180) * MAP_W / 360
        y0 = MAP_Y + (90 - lat0) * MAP_H / 180
        y2 = MAP_Y + (90 - lat2) * MAP_H / 180
        if abs(x2 - x0) > MAP_W / 2:
            x2 += -MAP_W if x2 > x0 else MAP_W
        # Height from the east-west distance: a north-south route with a
        # big bulge overshot its target and hooked back.
        d = abs(x2 - x0)
        band = 6 + (LIFT[1] - lift) / (LIFT[1] - LIFT[0]) * 40    # px from the edge
        if lat0 + lat2 >= 0:
            peak = min(y0, y2) - lift * d
            limit = MAP_Y + band
            if peak < limit:
                peak = limit
        else:
            peak = max(y0, y2) + lift * d
            limit = MAP_Y + MAP_H - band
            if peak > limit:
                peak = limit
        cx = (x0 + x2) / 2
        cy = 2 * peak - (y0 + y2) / 2      # quadratic curve peaks at t = 0.5
        pts = []
        for i in range(TRACK_POINTS + 1):
            t = i / TRACK_POINTS
            u = 1 - t
            pts.append((int(u * u * x0 + 2 * u * t * cx + t * t * x2) % MAP_W,
                        int(u * u * y0 + 2 * u * t * cy + t * t * y2)))
        return pts


class Polar:
    number = 2
    map_path = "/data/earth/polar.png"

    @staticmethod
    def xy(lon, lat):
        r = (90 - lat) / (90 - POLAR_MIN_LAT) * POLAR_R
        t = math.radians(lon - POLAR_LON0)
        return int(POLAR_CX + r * math.sin(t)), MAP_Y + int(POLAR_CY + r * math.cos(t))

    @staticmethod
    def visible(lat):
        return lat >= POLAR_MIN_LAT

    @staticmethod
    def track(a, b, lift):
        """Great circle (nearly straight over the pole on this projection)."""
        lon1, lat1 = CITIES[a]
        lon2, lat2 = CITIES[b]
        p1, l1, p2, l2 = (math.radians(v) for v in (lat1, lon1, lat2, lon2))
        v1 = (math.cos(p1) * math.cos(l1), math.cos(p1) * math.sin(l1), math.sin(p1))
        v2 = (math.cos(p2) * math.cos(l2), math.cos(p2) * math.sin(l2), math.sin(p2))
        om = math.acos(max(-1, min(1, v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2])))
        s = math.sin(om) or 1
        pts = []
        for i in range(TRACK_POINTS + 1):
            f = i / TRACK_POINTS
            ka, kb = math.sin((1 - f) * om) / s, math.sin(f * om) / s
            x = ka * v1[0] + kb * v2[0]
            y = ka * v1[1] + kb * v2[1]
            z = ka * v1[2] + kb * v2[2]
            lat = math.degrees(math.asin(max(-1, min(1, z))))
            # beyond the rim (south of POLAR_MIN_LAT): None, not drawn
            pts.append(Polar.xy(math.degrees(math.atan2(y, x)), lat)
                       if lat >= POLAR_MIN_LAT else None)
        return pts


VIEWS = (World, Polar)


# ---- drawing helpers ----------------------------------------------------------

# Missile outline pointing along +x: nose, body, tail fins (rotated per head).
_MISSILE = ((10, 0), (5, -2), (-5, -2), (-9, -6), (-8, -2), (-8, 2), (-9, 6), (-5, 2), (5, 2))


def _missile(fb, x, y, dx, dy):
    """Filled missile shape at (x, y) pointing along (dx, dy)."""
    n = (dx * dx + dy * dy) ** 0.5 or 1
    c, s = dx / n, dy / n
    coords = array.array("h")
    for px, py in _MISSILE:
        coords.append(int(round(px * c - py * s)))
        coords.append(int(round(px * s + py * c)))
    fb.poly(x, y, coords, 1, True)


_CLEAR = framebuf.FrameBuffer(bytearray(1), 2, 1, framebuf.MONO_HLSB)  # palette: 1 -> 0
_SPRITES = {}


def _mushroom(x, y, stage):
    """Mushroom cloud rising from (x, y) (tools/make_mushroom.py): its
    silhouette cleared to white on both planes, then its black pixels."""
    sp = _SPRITES.get(stage)
    if sp is None:
        w, h, ax, ay, mask, ink = sprite_mushroom.STAGES[stage]
        fmt = framebuf.MONO_HLSB
        sp = _SPRITES[stage] = (ax, ay, framebuf.FrameBuffer(bytearray(mask), w, h, fmt),
                                framebuf.FrameBuffer(bytearray(ink), w, h, fmt))
    ax, ay, mask, ink = sp
    display.black.blit(mask, x - ax, y - ay, 0, _CLEAR)
    display.red.blit(mask, x - ax, y - ay, 0, _CLEAR)
    display.black.blit(ink, x - ax, y - ay, 0)


def _ring(x, y, r):
    display.black.ellipse(x, y, r, r, 1)
    display.black.ellipse(x, y, r + 1, r + 1, 1)


@micropython.viper
def _red_off_under_black(red, black, n: int):
    """Black + red on one pixel is an undriven waveform table: black wins."""
    r = ptr8(red)
    b = ptr8(black)
    for i in range(n):
        r[i] = r[i] & (0xFF ^ b[i])


def _clear_text(font, plane, x, y, text):
    """Draw text by clearing bits (white digit on the red DEFCON box)."""
    pen = x << 4
    for ch in bitfont._clean(text):
        i = ord(ch) - font.FIRST
        w, off = font.WIDTHS[i], font.OFFSETS[i]
        rb = (w + 7) >> 3
        gx = (pen + 8) >> 4
        for r in range(font.HEIGHT):
            row = off + r * rb
            for c in range(w):
                if font.DATA[row + (c >> 3)] & (128 >> (c & 7)):
                    plane.pixel(gx + c, y + r, 0)
        pen += font.ADV16[i]


class WoprApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        super().__init__("WOPR")
        self.sleep_ms = 100
        self.next_update = 0
        self.next_quakes = 0
        self.last_full = -FULL_S
        self.trail = []
        self.quakes = []
        self.seen_big = set()
        self.iss = None
        self.step = 0
        self.missiles = []     # [launch_step, flight_steps, from, to, track id]
        self.tracks = {}       # (view number, track id) -> points
        self.defcon = None     # level shown at the last full refresh
        self.view = 0          # index into VIEWS
        self.view_since = None
        self.maps = {}         # view number -> (black, red) map planes
        self.want_switch = False   # User A pressed: other board next update
        self.want_salvo = False    # User B pressed: salvo at the US next update
        self.salvo_lands = None    # step the last US-bound salvo lands

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

    def _pick(self, sources, targets):
        """A launch site and target not already paired in the air (so tracks
        don't lie on top of each other); gives up after a few tries."""
        used = [(m[2], m[3]) for m in self.missiles]
        for _ in range(12):
            pair = (random.choice(sources), random.choice(targets))
            if pair not in used:
                return pair
        return pair

    def _launch(self, sources, targets, delay, flight=None):
        src, dst = self._pick(sources, targets)
        if flight is None:
            flight = FLIGHT[0] + random.getrandbits(8) % (FLIGHT[1] - FLIGHT[0] + 1)
        lift = LIFT[0] + (LIFT[1] - LIFT[0]) * random.getrandbits(8) / 255
        self.missiles.append([self.step + delay, flight, src, dst,
                              1000 + random.getrandbits(13) % 9000, lift])

    def _big_salvo(self, now=False):
        """4-8 missiles from the east side at US cities (launched over two
        updates, or all at once when `now`), arriving close together."""
        n = BIG_SALVO[0] + random.getrandbits(8) % (BIG_SALVO[1] - BIG_SALVO[0] + 1)
        # One flight time for the salvo (+-1 update), so it arrives together
        # and several missiles are close at once: that's when DEFCON hits 1.
        base = FLIGHT[0] + random.getrandbits(8) % (FLIGHT[1] - FLIGHT[0] - 1)
        for _ in range(n):
            self._launch(SIDES[1], USA, 0 if now else random.getrandbits(1),
                         base + random.getrandbits(1))
        lands = max(m[0] + m[1] for m in self.missiles[-n:])
        self.salvo_lands = max(self.salvo_lands or 0, lands)

    def _draw_lesson(self):
        """The lesson WOPR learned, in a white panel with a black border over
        the board; black/white only, so it goes out with the quick refresh
        (Kevin, 2026-11-07). Red under the panel isn't redrawn by a quick
        refresh and may show faintly until the next full one."""
        lines = ("A STRANGE GAME.", "", "THE ONLY WINNING MOVE IS", "NOT TO PLAY.")
        step = font_mono_huge.HEIGHT + 14
        x0, y0 = LESSON_X - 40, MAP_Y + 60
        w, h = display_width - 2 * x0, len(lines) * step + 60
        display.black.fill_rect(x0, y0, w, h, 0)
        display.red.fill_rect(x0, y0, w, h, 0)
        for i in range(3):
            display.black.rect(x0 + i, y0 + i, w - 2 * i, h - 2 * i, 1)
        y = y0 + 34
        for line in lines:
            if line:
                bitfont.draw(font_mono_huge, display._framebuffer_black, LESSON_X, y, line)
            y += step

    def _simulate(self):
        """Advance the made-up missiles one update. Returns True if one
        launched this step."""
        self.step += 1
        if self.step % SALVO_EVERY == 1:
            if random.getrandbits(8) % BIG_SALVO_ODDS == 0:   # big one at the US
                self._big_salvo()
            else:
                for _ in range(random.choice(SALVO_SIZES)):
                    side = random.getrandbits(8) % len(SIDES)
                    self._launch(SIDES[side], TARGETS[side],
                                 random.getrandbits(8) % SALVO_EVERY)
        keep = []
        for m in self.missiles:
            if self.step - m[0] <= m[1] + BLAST_STEPS:
                keep.append(m)
            else:
                for v in VIEWS:
                    self.tracks.pop((v.number, m[4]), None)
        self.missiles = keep
        return any(m[0] == self.step for m in self.missiles)

    def _incoming_usa(self):
        """(missiles in flight to US cities, how many of those are close)."""
        n = close = 0
        for m in self.missiles:
            age = self.step - m[0]
            if m[3] in USA and 0 <= age <= m[1]:
                n += 1
                if m[1] - age <= CLOSE_STEPS:
                    close += 1
        return n, close

    def _track(self, view, m):
        key = (view.number, m[4])
        pts = self.tracks.get(key)
        if pts is None:
            pts = self.tracks[key] = view.track(m[2], m[3], m[5])
        return pts

    # ---- drawing --------------------------------------------------------------

    def _draw_map(self, view):
        """Map planes from cache (decoding a PNG takes seconds)."""
        start, end = MAP_Y * ROW_BYTES, (MAP_Y + MAP_H) * ROW_BYTES
        if view.number not in self.maps:
            display.clear()
            display.draw_png(view.map_path, row=MAP_Y, col=0)
            self.maps[view.number] = (bytes(display._framebuffer_black[start:end]),
                                      bytes(display._framebuffer_red[start:end]))
        display.clear()
        black, red = self.maps[view.number]
        display._framebuffer_black[start:end] = black
        display._framebuffer_red[start:end] = red

    def _draw_missiles(self, view):
        """Returns [(track id, side name)] of tracks in flight."""
        fb = display.black
        flying = []
        for m in self.missiles:
            age = self.step - m[0]
            if age < 0:
                continue
            pts = self._track(view, m)
            if age <= m[1]:
                k = max(2, len(pts) * age // m[1])
                if view is World:   # dashes, like the film's world screen
                    for i in range(0, k - 1, 2):
                        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
                        if abs(x1 - x0) < MAP_W // 2:
                            fb.line(x0, y0, x1, y1, 1)
                            fb.line(x0, y0 + 1, x1, y1 + 1, 1)
                else:               # bundle of three streaks over the pole
                    seen = [p for p in pts if p] or [(0, 0), (1, 0)]  # all past the rim
                    (sx, sy), (ex, ey) = seen[0], seen[-1]
                    length = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5 or 1
                    nx, ny = -(ey - sy) / length, (ex - sx) / length
                    for off in (-5, 0, 5):
                        ox, oy = int(nx * off), int(ny * off)
                        for p0, p1 in zip(pts[:k - 1], pts[1:k]):
                            if p0 and p1:
                                fb.line(p0[0] + ox, p0[1] + oy, p1[0] + ox, p1[1] + oy, 1)
                                fb.line(p0[0] + ox + 1, p0[1] + oy, p1[0] + ox + 1, p1[1] + oy, 1)
                _dotted(fb, pts[k - 1:], PATH_GAP)      # faint path to the target
                if pts[-1]:
                    _dotted_circle(fb, pts[-1][0], pts[-1][1], TARGET_R)
                if pts[k - 1] and pts[k - 2]:
                    hx, hy = pts[k - 1]
                    px, py = pts[k - 2]
                    if abs(hx - px) > MAP_W // 2:       # just crossed the date line
                        px += MAP_W if hx > px else -MAP_W
                    _missile(fb, hx, hy, hx - px, hy - py)
                if pts[0]:          # label at the launch point: doesn't move
                    lx, ly = pts[0]
                    bitfont.draw(font_mono, display._framebuffer_black, lx + 6, ly + 4, "%d" % m[4])
                    if age <= 1:
                        _ring(lx, ly, 12)
                flying.append((m[4], _side_name(m[2])))
            elif pts[-1]:
                x, y = pts[-1]
                _mushroom(x, y, min(age - m[1], 2))   # explosion (Kevin, 2026-11-07)
        return flying

    def _draw_data(self, view):
        fb = display.black
        for lon, lat, mag, _ in self.quakes:
            if view.visible(lat):
                x, y = view.xy(lon, lat)
                r = int(2 + (mag - 2) ** 2 * 1.6)
                fb.ellipse(x, y, r, r, 1)
                if mag >= BIG_QUAKE:
                    fb.ellipse(x, y, r + 6, r + 6, 1)
        for lon, lat in self.trail:
            if view.visible(lat):
                x, y = view.xy(lon, lat)
                fb.ellipse(x, y, 3, 3, 1, True)
        if self.trail and view.visible(self.trail[-1][1]):
            x, y = view.xy(*self.trail[-1])
            _ring(x, y, 8)

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

    def _draw_text(self, view, flying, launched, incoming):
        black = display._framebuffer_black
        t = time.gmtime(self.iss["timestamp"] - UNIX_TO_MP_EPOCH)
        lat, lon = self.iss["latitude"], self.iss["longitude"]
        bitfont.draw(font_mono_big, black, 10, 6, "WOPR  // STRATEGIC DISPLAY")
        bitfont.draw(font_mono, black, 10, 42,
                     "%02d:%02dZ  TRACKS: %02d   INBOUND USA: %02d   SEISMIC: %d EVENTS M2.5+"
                     % (t[3], t[4], len(flying), incoming, len(self.quakes)))
        bitfont.draw(font_mono, black, 10, 64, "STS DSP %d GRID REF: %04d/%04d   LOC RF: NORAD" % (
            view.number, int(abs(lat) * 100) % 10000, int(abs(lon) * 100) % 10000))
        self._draw_defcon(self.defcon)
        banner = ("LAUNCH DETECTION" if launched else "MISSILE WARNING" if flying else "TRACKING")
        iss = "ISS %.1f%s %.1f%s" % (abs(lat), "N" if lat >= 0 else "S",
                                    abs(lon), "E" if lon >= 0 else "W")
        big = max(self.quakes, key=lambda q: q[2]) if self.quakes else None
        if view is World:
            bitfont.draw(font_thin, black, 24, MAP_Y + 330, banner)
            lines = []
            if big:
                lines.append("> STRONGEST EVENT: M%.1f %s" % (big[2], big[3].upper()))
            lines.append("> %s  ALT %.0f KM  %.0f KM/H" % (iss, self.iss["altitude"], self.iss["velocity"]))
            lines.append("> MAP: NATURAL EARTH (NATURALEARTHDATA.COM)  DATA: WHERETHEISS.AT, USGS")
            bitfont.draw_lines(font_mono, black, lines, 10, MAP_Y + MAP_H + 8,
                               display_width - 20, max_lines=3)
        else:
            words = banner.split(" ", 1)
            bitfont.draw(font_thin, black, 20, MAP_Y + 6, words[0])
            if len(words) > 1:
                bitfont.draw(font_thin, black, 20, MAP_Y + 52, words[1])
            y = MAP_Y + 130
            bitfont.draw(font_mono, black, 10, y, "TRK   SIDE")
            for tid, side in flying[:14]:
                y += 20
                bitfont.draw(font_mono, black, 10, y, "%d  %s" % (tid, side))
            right = ["INBOUND USA: %d" % incoming, "", iss, "ALT %.0f KM" % self.iss["altitude"], ""]
            if big:
                right.append("M%.1f %s" % (big[2], big[3].upper()[-14:]))
            right.append("%d EVENTS M2.5+" % len(self.quakes))
            for i, line in enumerate(right):
                bitfont.draw(font_mono, black, display_width - 212, MAP_Y + 130 + i * 20, line)
            bitfont.draw(font_mono, black, 10, display_height - 22,
                         "MAP: NATURAL EARTH  DATA: WHERETHEISS.AT, USGS")

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
            print("wopr: update failed:", repr(ex))
            leds.fill((2, 0, 0))
            leds.write()
            self.next_update = time.time() + RETRY_S
            return
        leds.fill((0, 0, 0))
        leds.write()
        if self.step == 0:
            for _ in range(PREROLL):
                self._simulate()
        launched = self._simulate()
        if self.want_salvo:     # User B
            self.want_salvo = False
            self._big_salvo(now=True)
            launched = True
        lesson = self.salvo_lands is not None and self.step > self.salvo_lands + BLAST_STEPS
        if lesson:              # the US salvo has landed: clear the board
            self.salvo_lands = None
            self.missiles = []
            self.tracks = {}
        now = time.time()
        switched = False
        if self.view_since is None:
            self.view_since = now
        elif self.want_switch or now - self.view_since >= VIEW_S:
            self.view = (self.view + 1) % len(VIEWS)
            self.view_since = now
            switched = True
        self.want_switch = False
        view = VIEWS[self.view]
        incoming, close = self._incoming_usa()
        level = _defcon(incoming, close)
        rising = self.defcon is not None and level < self.defcon
        full = (force_full or self.launched or new_big or switched or rising
                or self.defcon is None or now - self.last_full >= FULL_S) and not lesson
        if full:
            self.last_full = now
            self.defcon = level
        self._draw_map(view)
        self._draw_data(view)
        flying = self._draw_missiles(view)
        self._draw_text(view, flying, launched, incoming)
        if lesson:
            self._draw_lesson()
            print("wopr: the only winning move is not to play")
        _red_off_under_black(display._framebuffer_red, display._framebuffer_black, PLANE_BYTES)
        print("wopr: board %d, %d tracks, %d inbound USA, DEFCON %d (now %d), %d quakes, %s refresh" % (
            view.number, len(flying), incoming, self.defcon, level, len(self.quakes),
            "full" if full else "fast"))
        display.update(fast=not full, keep_red=not full)
        self.next_update = now + UPDATE_S
        gc.collect()

    def run(self):
        if self.launched or time.time() >= self.next_update:
            self._update()
        elif UserA.pressed():
            # Remembered if the panel is still busy: switches when it's free.
            self.want_switch = True
            self.next_update = 0        # the switch itself forces a full refresh
        elif UserB.pressed():
            self.want_salvo = True      # rising DEFCON forces a full refresh
            self.next_update = 0
