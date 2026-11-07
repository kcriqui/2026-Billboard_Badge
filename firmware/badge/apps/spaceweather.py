"""Space Weather: a full-screen dithered plasma driven by the solar wind.

No solid areas: the whole screen is an ordered-dither of white, red and black
(lib/plasma.py), in two layers:
  - red, deep and slow: amount set by the Kp index / storm level; redrawn
    only with a full refresh (red needs one) on launch, after FAST_IN_A_ROW
    fast updates (red fades under fast refreshes), and when the storm level
    changes - the flash is the "event".
  - black, the surface: redrawn every UPDATE_S with a fast refresh that
    leaves red alone (keep_red); its waviness follows southward Bz, its
    density Bt, and how far it drifts each update the solar wind speed, so
    the previous frames linger as ghosts.

A small caption (bitmap font) shows the numbers; User B hides/shows it.
User A: update now.

Data: NOAA Space Weather Prediction Center (services.swpc.noaa.gov):
solar wind speed and magnetic field summaries, estimated planetary Kp, and
the NOAA G-scale.
"""

import gc
import json
import os
import time

from apps.base_app import BaseApp
from lib import bitfont, font_small, net, plasma, wifi
from lib.button import UserA, UserB
from lib.epd import display
from lib.led_bar import leds

UPDATE_S = 3 * 60
FULL_S = 60 * 60
# Red fades under fast refreshes (fringe fields from the driven black/white
# neighbours of each dithered red dot), so top it up with a full refresh
# after this many fast ones (4 x 3 min -> every 15 min).
FAST_IN_A_ROW = 4
# Pulses per fast refresh (driver B default is 3); fewer = less disturbance
# of the red, slightly lighter black / more ghosting.
FAST_PASSES = 2
RETRY_S = 60
SWPC = "https://services.swpc.noaa.gov"
PLANE_BYTES = plasma.W * plasma.H // 8
LOG_PATH = "/data/spaceweather.log"
LOG_MAX_BYTES = 8192


def log(line):
    """print() and append to /data/spaceweather.log (survives a reset;
    the only record of updates while battery mode sleeps)."""
    print("spaceweather:", line)
    try:
        try:
            if os.stat(LOG_PATH)[6] > LOG_MAX_BYTES:
                os.remove(LOG_PATH)
        except OSError:
            pass
        with open(LOG_PATH, "a") as f:
            f.write("%d %s\n" % (time.time(), line))
    except OSError:
        pass


def _summary(path):
    data = json.loads(bytes(net.https_get(SWPC + path, 4096)))
    return data[0] if isinstance(data, list) else data


class SpaceWeatherApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        super().__init__("Space Weather")
        self.sleep_ms = 100
        self.next_update = 0
        self.last_full = -FULL_S
        self.step = 0
        self.fast_in_a_row = 0
        self.wx = {}
        self.level = None        # (storm?, G) at the last full refresh
        self.red = None          # cached red plane between full refreshes
        self.caption = True

    def _fetch(self):
        wifi.connect()
        speed = _summary("/products/summary/solar-wind-speed.json")
        mag = _summary("/products/summary/solar-wind-mag-field.json")
        kp_rows = json.loads(bytes(net.https_get(SWPC + "/json/planetary_k_index_1m.json", 64 * 1024)))
        scales = json.loads(bytes(net.https_get(SWPC + "/products/noaa-scales.json", 8192)))
        g = int(scales["0"]["G"]["Scale"] or 0)
        self.wx = {"speed": speed.get("proton_speed"), "bt": mag.get("bt"),
                   "bz": mag.get("bz_gsm"), "kp": kp_rows[-1].get("estimated_kp"),
                   "g": g, "time": speed.get("time_tag", "")}
        kp_rows = None
        gc.collect()

    def _draw_caption(self):
        wx = self.wx
        bz = int(wx.get("bz") or 0)
        lines = [
            "SPACE WEATHER   %s UTC" % (wx.get("time", "")[11:16]),
            "wind %s km/s   Bz %+d nT (%s)   Bt %s nT" % (
                wx.get("speed"), bz, "south" if bz < 0 else "north", wx.get("bt")),
            "Kp %.1f   storm level G%d   data: NOAA SWPC" % (wx.get("kp") or 0, wx.get("g") or 0),
        ]
        x, y, pad = 8, plasma.H - 3 * (font_small.HEIGHT + 2) - 12, 4
        w = max(bitfont.width(font_small, l) for l in lines) + 2 * pad
        h = 3 * (font_small.HEIGHT + 2) + 2 * pad
        display.black.fill_rect(x - pad, y - pad, w, h, 0)   # small clear box
        display.red.fill_rect(x - pad, y - pad, w, h, 0)
        bitfont.draw_lines(font_small, display._framebuffer_black, lines, x, y, w)

    def _update(self, force_full=False):
        if not display.is_done_updating():
            self.next_update = time.time() + 5
            return
        leds.fill((0, 0, 2))
        leds.write()
        try:
            self._fetch()
        except Exception as ex:  # network hiccup: keep the old picture
            log("update failed: %r" % (ex,))
            leds.fill((2, 0, 0))
            leds.write()
            self.next_update = time.time() + RETRY_S
            return
        leds.fill((0, 0, 0))
        leds.write()
        self.step += 1
        red_p, black_p = plasma.from_weather(self.wx, self.step)
        level = ((self.wx.get("g") or 0) >= 1 or (self.wx.get("kp") or 0) >= 5, self.wx.get("g"))
        full = (force_full or self.launched or self.red is None or level != self.level
                or self.fast_in_a_row >= FAST_IN_A_ROW
                or time.time() - self.last_full >= FULL_S)
        self.fast_in_a_row = 0 if full else self.fast_in_a_row + 1
        t = time.ticks_ms()
        if full:
            plasma.layer(display._framebuffer_red, red_p)
            self.red = bytes(display._framebuffer_red)
            self.level = level
            self.last_full = time.time()
        else:
            display._framebuffer_red[:] = self.red
        plasma.layer(display._framebuffer_black, black_p, avoid=display._framebuffer_red)
        if self.caption:
            self._draw_caption()
        log("Kp %s, wind %s, drew in %d ms, %s refresh" % (
            self.wx.get("kp"), self.wx.get("speed"),
            time.ticks_diff(time.ticks_ms(), t), "full" if full else "fast"))
        display.update(fast=not full, keep_red=not full,
                       passes=None if full else FAST_PASSES)
        self.next_update = time.time() + UPDATE_S
        gc.collect()

    def run(self):
        if self.launched or time.time() >= self.next_update:
            self._update()
        elif UserA.pressed():
            self._update()
        elif UserB.pressed():
            self.caption = not self.caption
            self._update(force_full=True)  # red behind the caption needs a full refresh
