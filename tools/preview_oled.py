#!/usr/bin/env python3
"""Preview the OLED screens on the laptop using the badge's own drawing code.

    python3 tools/preview_oled.py out.png

Runs firmware/badge/lib/oled.py under CPython with small stand-ins for
MicroPython (framebuf, machine) and renders Oled.render() at real pixels:
long and short names in the menu, and an app running. Needs Pillow.
"""

import builtins
import pathlib
import sys
import time
import types

from PIL import Image, ImageDraw

REPO = pathlib.Path(__file__).resolve().parent.parent
SCALE = 4
MONO_VLSB, MONO_HLSB = 0, 1


class FrameBuffer:
    """Enough of framebuf.FrameBuffer for lib/oled.py."""

    def __init__(self, buf, w, h, fmt):
        self.buf, self.w, self.h, self.fmt = buf, w, h, fmt

    def _at(self, x, y):
        if self.fmt == MONO_VLSB:
            return (y >> 3) * self.w + x, 1 << (y & 7)
        return y * ((self.w + 7) >> 3) + (x >> 3), 0x80 >> (x & 7)

    def pixel(self, x, y, c=None):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return 0
        i, bit = self._at(x, y)
        if c is None:
            return 1 if self.buf[i] & bit else 0
        self.buf[i] = self.buf[i] | bit if c else self.buf[i] & ~bit

    def fill(self, c):
        self.buf[:] = bytes([0xFF if c else 0]) * len(self.buf)

    def fill_rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.pixel(xx, yy, c)

    def hline(self, x, y, w, c):
        self.fill_rect(x, y, w, 1, c)

    def rect(self, x, y, w, h, c):
        self.hline(x, y, w, c)
        self.hline(x, y + h - 1, w, c)
        self.fill_rect(x, y, 1, h, c)
        self.fill_rect(x + w - 1, y, 1, h, c)

    def blit(self, src, x, y, key=-1):
        for sy in range(src.h):
            for sx in range(src.w):
                c = src.pixel(sx, sy)
                if c != key:
                    self.pixel(x + sx, y + sy, c)


fb = types.ModuleType("framebuf")
fb.FrameBuffer, fb.MONO_VLSB, fb.MONO_HLSB = FrameBuffer, MONO_VLSB, MONO_HLSB
sys.modules["framebuf"] = fb
mc = types.ModuleType("machine")
mc.I2C = mc.Pin = None
sys.modules["machine"] = mc
builtins.ptr8 = lambda b: b
time.ticks_ms = lambda: int(time.monotonic() * 1000)
sys.modules["micropython"] = types.SimpleNamespace(viper=lambda f: f, native=lambda f: f, const=lambda x: x)
sys.modules["lib.wifi"] = types.ModuleType("lib.wifi")
sys.path.insert(0, str(REPO / "firmware/badge"))
from lib import oled as oled_mod  # noqa: E402

W, H = oled_mod.W, oled_mod.H
BATT = ("ACCD", 2, 78)
USB = ("ACCD", 2, None)
LONG = ("Some-very-long-network", 4, 9)
CASES = [
    ("Space Weather, menu", "Space Weather", True, 2, BATT),
    ("WOPR, menu", "WOPR", True, 3, BATT),
    ("XKCD, running", "XKCD", False, 4, USB),
    ("Gallery, long SSID", "Gallery", True, 0, LONG),
    ("Nametag, no WiFi", "Nametag", True, 1, ("no WiFi", 0, 100)),
    ("Space Weather, running", "Space Weather", False, 2, USB),
]


def panel(o, label):
    out = Image.new("RGB", (W * SCALE + 16, H * SCALE + 30), (40, 40, 40))
    d = ImageDraw.Draw(out)
    for y in range(H):
        for x in range(W):
            c = (200, 230, 255) if o.fb.pixel(x, y) else (8, 8, 12)
            x0, y0 = 8 + x * SCALE, 26 + y * SCALE
            d.rectangle((x0, y0, x0 + SCALE - 2, y0 + SCALE - 2), fill=c)
    d.text((8, 6), label, fill=(255, 255, 255))
    return out


def main():
    o = oled_mod.Oled()
    shots = []
    for label, name, menu, idx, status in CASES:
        o._status = status
        o.render(name, menu, idx, 5)
        shots.append(panel(o, label))
    for _ in range(60):
        o.life_advance()
    shots[-1] = panel(o, "Idle: Game of Life, 60 generations")
    w, h = shots[0].size
    sheet = Image.new("RGB", (w * 3, h * 2), (40, 40, 40))
    for i, s in enumerate(shots):
        sheet.paste(s, ((i % 3) * w, (i // 3) * h))
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "oled_preview.png")


if __name__ == "__main__":
    main()
