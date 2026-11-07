"""Long Exposure Earth: the ISS and earthquakes on a red world map.

Every UPDATE_S the ISS position is added; only the last orbit is drawn in
black, so older positions fade out as e-paper ghosts left by the fast
refresh (keep_red=True leaves the red coastlines untouched). Earthquakes
(USGS, M2.5+ in the past day) are refreshed every QUAKE_S and drawn as rings
sized by magnitude. A full refresh - the flash - starts a new "exposure" on
launch, every FULL_S, and when a new M6+ quake appears.

User A: update now. User B: full refresh now (wipe the ghosts).

Data: ISS position from wheretheiss.at; earthquakes from the USGS
Earthquake Hazards Program feed.
Map: Made with Natural Earth. Free vector and raster map data @
naturalearthdata.com (data/earth/world.png, made by tools/make_world_map.py).
"""

import gc
import json
import time

import lvgl

from apps.base_app import BaseApp
from lib import net, wifi
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

_BLACK = lvgl.color_hex(0x000000)
_WHITE = lvgl.color_hex(0xFFFFFF)


def _xy(lon, lat):
    return int((lon + 180) * MAP_W / 360), MAP_Y + int((90 - lat) * MAP_H / 180)


def _mark(x, y, r, fill=False):
    """Black circle; clears red under it (black + red = an undriven pixel)."""
    display.black.ellipse(x, y, r, r, 1, fill)
    display.red.ellipse(x, y, r, r, 0, fill)


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
        self._ui = None

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

    # ---- drawing --------------------------------------------------------------

    def _draw_map(self):
        """Map planes from cache (decoding the PNG takes seconds)."""
        start, end = MAP_Y * ROW_BYTES, (MAP_Y + MAP_H) * ROW_BYTES
        if self._map is None:
            display.clear()
            display.draw_png(MAP_PATH, row=MAP_Y, col=0)
            self._map = (bytes(display._framebuffer_black[start:end]),
                         bytes(display._framebuffer_red[start:end]))
        display.clear()
        display._framebuffer_black[start:end] = self._map[0]
        display._framebuffer_red[start:end] = self._map[1]

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

    def _ensure_ui(self):
        if self._ui:
            return
        scr = lvgl.obj()
        scr.remove_style_all()
        scr.set_style_bg_opa(lvgl.OPA.TRANSP, 0)
        boxes = []
        for top, h in ((0, MAP_Y), (MAP_Y + MAP_H, display_height - MAP_Y - MAP_H)):
            box = lvgl.obj(scr)
            box.remove_style_all()
            box.set_pos(0, top)
            box.set_size(display_width, h)
            box.set_style_bg_color(_WHITE, 0)
            box.set_style_bg_opa(lvgl.OPA.COVER, 0)
            boxes.append(box)
        title = lvgl.label(boxes[0])
        title.set_pos(10, 6)
        title.set_text("LONG EXPOSURE EARTH")
        title.set_style_text_font(lvgl.font_montserrat_28, 0)
        title.set_style_text_color(_BLACK, 0)
        sub = lvgl.label(boxes[0])
        sub.set_pos(10, 46)
        sub.set_style_text_font(lvgl.font_montserrat_16, 0)
        sub.set_style_text_color(_BLACK, 0)
        foot = lvgl.label(boxes[1])
        foot.set_pos(10, 8)
        foot.set_width(display_width - 20)
        foot.set_style_text_font(lvgl.font_montserrat_16, 0)
        foot.set_style_text_color(_BLACK, 0)
        self._ui = (scr, boxes, sub, foot)

    def _draw_text(self):
        self._ensure_ui()
        scr, boxes, sub, foot = self._ui
        t = time.gmtime(self.iss["timestamp"] - UNIX_TO_MP_EPOCH)
        sub.set_text("%04d-%02d-%02d %02d:%02d UTC    ISS over the last orbit  +  earthquakes M2.5+, past 24 h"
                     % (t[0], t[1], t[2], t[3], t[4]))
        lines = []
        if self.quakes:
            big = max(self.quakes, key=lambda q: q[2])
            lines.append("Strongest quake: M%.1f %s   (%d quakes)" % (big[2], big[3], len(self.quakes)))
        lines.append("ISS lat %.1f, lon %.1f   altitude %.0f km   %.0f km/h" % (
            self.iss["latitude"], self.iss["longitude"], self.iss["altitude"], self.iss["velocity"]))
        lines.append("Map: Natural Earth (naturalearthdata.com)   Data: wheretheiss.at, USGS")
        foot.set_text("\n".join(lines))
        lvgl.screen_load(scr)
        scr.update_layout()
        display.lv_display.inv_p = 0
        for box in boxes:
            box.invalidate()
        lvgl.refr_now(display.lv_display)

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
        self._draw_map()
        self._draw_data()
        self._draw_text()
        full = (force_full or self.launched or new_big
                or time.time() - self.last_full >= FULL_S)
        if full:
            self.last_full = time.time()
        print("earth: ISS %.1f %.1f, %d quakes, %s refresh%s" % (
            self.iss["latitude"], self.iss["longitude"], len(self.quakes),
            "full" if full else "fast", " (new M6+ quake)" if new_big else ""))
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
