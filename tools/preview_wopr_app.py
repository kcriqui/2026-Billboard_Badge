#!/usr/bin/env python3
"""Render the WOPR app's real drawing code on the laptop.

    python3 tools/preview_wopr_app.py out.png [--salvo] [--steps N] [--lesson]

Runs firmware/badge/apps/wopr.py under CPython with small stand-ins for
MicroPython (framebuf, viper, the display), feeds it made-up ISS/quake data,
advances the missile simulation and draws both boards (world, polar) as the
badge would, side by side. --salvo fires a User-B salvo at the US first;
--lesson draws the lesson panel too. Ghosting is not simulated: this is one
frame as drawn into the black/red planes. Needs Pillow.
"""

import argparse
import array
import builtins
import math
import pathlib
import random
import sys
import types

from PIL import Image

REPO = pathlib.Path(__file__).resolve().parent.parent
BADGE = REPO / "firmware/badge"
W, H = 960, 672

# ---- MicroPython stand-ins ------------------------------------------------------

mp = types.ModuleType("micropython")
mp.viper = mp.native = lambda f: f
mp.const = lambda x: x
sys.modules["micropython"] = mp
builtins.ptr8 = lambda b: b

MONO_HLSB, MONO_VLSB = 0, 1


class FrameBuffer:
    """Enough of framebuf.FrameBuffer (MONO_HLSB) for WOPR."""

    def __init__(self, buf, w, h, fmt=MONO_HLSB):
        self.buf, self.w, self.h = buf, w, h

    def pixel(self, x, y, c=None):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return 0
        i, bit = y * ((self.w + 7) // 8) + (x >> 3), 0x80 >> (x & 7)   # rows padded to bytes
        if c is None:
            return 1 if self.buf[i] & bit else 0
        if c:
            self.buf[i] |= bit
        else:
            self.buf[i] &= ~bit & 0xFF

    def fill(self, c):
        for i in range(len(self.buf)):
            self.buf[i] = 0xFF if c else 0

    def fill_rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.pixel(xx, yy, c)

    def rect(self, x, y, w, h, c, f=False):
        if f:
            return self.fill_rect(x, y, w, h, c)
        for xx in range(x, x + w):
            self.pixel(xx, y, c)
            self.pixel(xx, y + h - 1, c)
        for yy in range(y, y + h):
            self.pixel(x, yy, c)
            self.pixel(x + w - 1, yy, c)

    def line(self, x0, y0, x1, y1, c):
        n = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(n + 1):
            self.pixel(round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n), c)

    def ellipse(self, x, y, xr, yr, c, f=False, m=0xF):
        if f:
            for yy in range(-yr, yr + 1):
                span = int(xr * math.sqrt(max(0, 1 - (yy / yr) ** 2))) if yr else xr
                for xx in range(-span, span + 1):
                    self.pixel(x + xx, y + yy, c)
            return
        n = max(8, int(2 * math.pi * max(xr, yr)))
        for k in range(n):
            a = 2 * math.pi * k / n
            self.pixel(round(x + xr * math.cos(a)), round(y + yr * math.sin(a)), c)

    def blit(self, src, x, y, key=-1, palette=None):
        for sy in range(src.h):
            for sx in range(src.w):
                col = src.pixel(sx, sy)
                if col == key:
                    continue
                self.pixel(x + sx, y + sy, palette.pixel(col, 0) if palette else col)

    def poly(self, x, y, coords, c, f=False):
        pts = [(x + coords[i], y + coords[i + 1]) for i in range(0, len(coords), 2)]
        if f:
            ys = [p[1] for p in pts]
            for yy in range(min(ys), max(ys) + 1):
                xs = []
                for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
                    if (ay <= yy < by) or (by <= yy < ay):
                        xs.append(ax + (yy - ay) * (bx - ax) / (by - ay))
                xs.sort()
                for a, b in zip(xs[::2], xs[1::2]):
                    for xx in range(round(a), round(b) + 1):
                        self.pixel(xx, yy, c)
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            self.line(ax, ay, bx, by, c)


fbmod = types.ModuleType("framebuf")
fbmod.FrameBuffer, fbmod.MONO_HLSB, fbmod.MONO_VLSB = FrameBuffer, MONO_HLSB, MONO_VLSB
sys.modules["framebuf"] = fbmod


class Display:
    def __init__(self):
        self._framebuffer_black = bytearray(W * H // 8)
        self._framebuffer_red = bytearray(W * H // 8)
        self.black = FrameBuffer(self._framebuffer_black, W, H)
        self.red = FrameBuffer(self._framebuffer_red, W, H)
        self.updates = []

    def clear(self):
        self.black.fill(0)
        self.red.fill(0)

    def draw_png(self, path, row=0, col=0):
        im = Image.open(BADGE / path.lstrip("/"))
        px = im.load()
        for y in range(im.height):
            for x in range(im.width):
                v = px[x, y]
                if v == 2:
                    self.red.pixel(col + x, row + y, 1)
                elif v == 1:
                    self.black.pixel(col + x, row + y, 1)

    def is_done_updating(self):
        return True

    def update(self, **kw):
        self.updates.append(kw)


display = Display()
for name in ("apps.base_app", "lib.button", "lib.epd", "lib.led_bar", "lib.net", "lib.wifi"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["apps.base_app"].BaseApp = type("BaseApp", (), {"__init__": lambda self, n: setattr(self, "launched", True)})
sys.modules["lib.button"].UserA = sys.modules["lib.button"].UserB = None
epd = sys.modules["lib.epd"]
epd.display, epd.display_width, epd.display_height = display, W, H
sys.modules["lib.led_bar"].leds = types.SimpleNamespace(fill=lambda c: None, write=lambda: None)
sys.path.insert(0, str(BADGE))
import apps.wopr as wopr  # noqa: E402


def planes_to_image():
    im = Image.new("RGB", (W, H), (255, 255, 255))
    px = im.load()
    for y in range(H):
        for x in range(W):
            if display.black.pixel(x, y):
                px[x, y] = (0, 0, 0)
            elif display.red.pixel(x, y):
                px[x, y] = (205, 25, 30)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--steps", type=int, default=6, help="updates after the pre-roll")
    ap.add_argument("--salvo", action="store_true", help="fire a User-B salvo first")
    ap.add_argument("--lesson", action="store_true", help="draw the lesson panel")
    args = ap.parse_args()
    random.seed(5)
    app = wopr.WoprApp()
    app.iss = {"latitude": 12.4, "longitude": -61.0, "altitude": 418, "velocity": 27580, "timestamp": 1794100000}
    app.trail = [(((-100 + 360 * i / 31) + 180) % 360 - 180, 51.6 * math.sin(2 * math.pi * i / 31)) for i in range(20)]
    rnd = random.Random(2)
    app.quakes = [(rnd.uniform(-180, 180), rnd.uniform(-50, 60), rnd.uniform(2.5, 5.5), "somewhere") for _ in range(25)]
    app.quakes.append((142.0, 38.0, 6.3, "off the coast of Honshu, Japan"))
    for _ in range(wopr.PREROLL):
        app._simulate()
    if args.salvo:
        app._big_salvo(now=True)
    for _ in range(args.steps):
        app._simulate()
    incoming, close = app._incoming_usa()
    app.defcon = wopr._defcon(incoming, close)
    shots = []
    for view in wopr.VIEWS:
        app._draw_map(view)
        app._draw_data(view)
        flying = app._draw_missiles(view)
        app._draw_text(view, flying, False, incoming)
        if args.lesson:
            app._draw_lesson()
        wopr._red_off_under_black(display._framebuffer_red, display._framebuffer_black, wopr.PLANE_BYTES)
        shots.append(planes_to_image())
    sheet = Image.new("RGB", (W * 2 + 20, H), (60, 60, 60))
    sheet.paste(shots[0], (0, 0))
    sheet.paste(shots[1], (W + 20, 0))
    sheet.save(args.out)
    print("step %d: %d inbound USA, %d close -> DEFCON %d" % (app.step, incoming, close, app.defcon))


if __name__ == "__main__":
    main()
