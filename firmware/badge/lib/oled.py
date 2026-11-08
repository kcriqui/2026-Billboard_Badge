"""Menu helper on a 128x64 SSD1306-style OLED on the SAO I2C bus.

Currently a MachineIdeas "SAO OLED" (0x3C or 0x3D by its address option),
which replaced an Adafruit #326 that broke. Any 128x64 panel at either
address works.

A status bar on top (signal bars, network, battery or USB) and the app's
name below it, as large as fits; two-word names too long for one line take
two. In the menu, dots along the bottom show the position. Layout chosen by
Kevin from previews (tools/preview_oled.py).

A while after the menu closes, Conway's Game of Life fills the screen until
the next menu press. The OLED stays on while battery mode sleeps
(lib/power.py), and Life steps slowly through the sleep.

If no OLED answers, the task waits and looks again every RETRY_S, so the
badge works the same without one.

Wiring: SAO pin 1 3V3, 2 GND, 3 SDA (GPIO17), 4 SCL (GPIO18).
"""

import asyncio as aio
import os
import time

import framebuf
import micropython
from machine import I2C, Pin
from micropython import const

from lib import (bitfont, font_oled_big, font_oled_huge, font_oled_large,
                 font_oled_mid, font_oled_small, wifi)

ADDRS = (0x3C, 0x3D)
W, H = 128, 64
FLIP = False            # True if the OLED is mounted upside down
STATUS_EVERY_MS = 10000
RETRY_S = 30
BAR_RULE = 12           # the status bar's rule; the name area starts below it
DOTS_TOP = 56           # the name area ends here in the menu
LIFE_AFTER_MS = 8000    # name stays this long after the menu closes, then Life
LIFE_MS = 250           # one generation this often while awake
_LIFE_W = const(64)     # cells; each is 2x2 pixels
_LIFE_H = const(32)
_LIFE_CELLS = const(2048)
LIFE_DENSITY = 77       # of 256: share of cells alive in a new soup
NAME_FONTS = (font_oled_huge, font_oled_large, font_oled_big, font_oled_mid)

# LiPo resting voltage -> rough charge %, read at the regulator input.
_LIPO = ((4.20, 100), (4.10, 90), (4.00, 80), (3.90, 65), (3.80, 50),
         (3.70, 35), (3.60, 20), (3.50, 10), (3.30, 0))


def battery_pct(volts):
    if volts >= _LIPO[0][0]:
        return 100
    for (v1, p1), (v2, p2) in zip(_LIPO, _LIPO[1:]):
        if volts >= v2:
            return int(p2 + (p1 - p2) * (volts - v2) / (v1 - v2))
    return 0


@micropython.viper
def _life_step(cur, nxt):
    """One generation on a wrap-around grid (one byte per cell)."""
    a = ptr8(cur)
    b = ptr8(nxt)
    for y in range(_LIFE_H):
        y0 = y * _LIFE_W
        up = ((y + _LIFE_H - 1) & (_LIFE_H - 1)) * _LIFE_W
        dn = ((y + 1) & (_LIFE_H - 1)) * _LIFE_W
        for x in range(_LIFE_W):
            xl = (x + _LIFE_W - 1) & (_LIFE_W - 1)
            xr = (x + 1) & (_LIFE_W - 1)
            n = (a[up + xl] + a[up + x] + a[up + xr] + a[y0 + xl] + a[y0 + xr]
                 + a[dn + xl] + a[dn + x] + a[dn + xr])
            v = 0
            if n == 3:
                v = 1
            elif n == 2:
                v = a[y0 + x]
            b[y0 + x] = v


@micropython.viper
def _life_hash(cur) -> int:
    a = ptr8(cur)
    h = 0
    for i in range(_LIFE_CELLS):
        h = ((h * 31) + a[i]) & 0x3FFFFFFF
    return h


@micropython.viper
def _life_draw(cur, buf):
    """Cells to the panel's page buffer, each as 2x2 pixels."""
    a = ptr8(cur)
    o = ptr8(buf)
    for page in range(8):
        for x in range(_LIFE_W):
            v = 0
            for j in range(4):
                if a[(page * 4 + j) * _LIFE_W + x]:
                    v = v | (3 << (2 * j))
            at = page * 128 + 2 * x
            o[at] = v
            o[at + 1] = v


class Oled:
    def __init__(self):
        self.i2c = None
        self.addr = None
        self.on = False
        self.buf = bytearray(W * H // 8)
        self.fb = framebuf.FrameBuffer(self.buf, W, H, framebuf.MONO_VLSB)
        self._last = None
        self._status = ("", 0, None)   # network, signal bars, battery % or None on USB
        self._status_at = None
        self._page = None        # what the name screen shows, and since when
        self._page_at = 0
        self._in_life = False
        self._life = bytearray(_LIFE_CELLS)
        self._life_next = bytearray(_LIFE_CELLS)
        self._life_at = None     # ticks_ms of the last generation
        self._life_gen = 0
        self._life_limit = 1     # cycle check: compare with a saved state,
        self._life_mark = -1     # saved again at each power of two (Brent)

    # --- hardware -------------------------------------------------------
    def find(self):
        """Look for the OLED; True if found (and initialised)."""
        try:
            i2c = I2C(0, scl=Pin(18), sda=Pin(17), freq=400000)
            found = i2c.scan()
            for addr in ADDRS:
                if addr in found:
                    break
            else:
                return False
            self.i2c, self.addr = i2c, addr
            # Page addressing (0x20, 0x02): the mode every SSD1306-style
            # controller has, and the one this panel was tested in.
            self._cmd(0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14,
                      0x20, 0x02, 0xA0 if FLIP else 0xA1, 0xC0 if FLIP else 0xC8,
                      0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6)
        except OSError as ex:
            print("oled: init failed:", repr(ex))
            self.i2c = None
            return False
        self.on = False
        self._last = None
        print("oled: ready at 0x%02X" % self.addr)
        return True

    def _cmd(self, *cmds):
        for c in cmds:
            self.i2c.writeto(self.addr, bytes((0x80, c)))

    def show(self):
        for page in range(H // 8):
            self._cmd(0xB0 | page, 0x00, 0x10)
            self.i2c.writeto(self.addr, b"\x40" + self.buf[page * W:(page + 1) * W])

    def power(self, on):
        self._cmd(0xAF if on else 0xAE)
        self.on = on

    # --- drawing --------------------------------------------------------
    def text(self, font, x, y, s):
        """Draw a bitfont string with its top-left at (x, y)."""
        pen = x << 4
        for ch in bitfont._clean(s):
            i = ord(ch)
            if i < font.FIRST or i > font.LAST:
                i = ord("?")
            i -= font.FIRST
            w = font.WIDTHS[i]
            off = font.OFFSETS[i]
            size = ((w + 7) >> 3) * font.HEIGHT
            glyph = framebuf.FrameBuffer(bytearray(font.DATA[off:off + size]),
                                         w, font.HEIGHT, framebuf.MONO_HLSB)
            self.fb.blit(glyph, (pen + 8) >> 4, y, 0)
            pen += font.ADV16[i]

    def centered(self, font, cy, s, x0=0, x1=W):
        w = bitfont.width(font, s)
        self.text(font, x0 + (x1 - x0 - w) // 2, cy - font.HEIGHT // 2, s)

    def _read_status(self):
        from lib import power as power_mod
        net, bars = "no WiFi", 0
        if wifi.is_connected():
            net, bars = "WiFi on", 1
            try:
                net = wifi._wlan.config("ssid")
                rssi = wifi._wlan.status("rssi")
                bars = 4 if rssi > -55 else 3 if rssi > -65 else 2 if rssi > -75 else 1
            except Exception:
                pass
        pct = battery_pct(power_mod.input_volts()) if power_mod.on_battery() else None
        return net, bars, pct

    def _status_bar(self):
        net, bars, pct = self._status
        for i in range(4):
            x = i * 4
            if i < bars:
                h = 3 + i * 2
                self.fb.fill_rect(x, 9 - h + 1, 3, h, 1)
            else:
                self.fb.hline(x, 9, 3, 1)
        if pct is None:
            label, right = "USB", W
        else:
            self.fb.rect(W - 19, 0, 17, 10, 1)
            self.fb.fill_rect(W - 2, 3, 2, 4, 1)
            fill = (14 * pct + 50) // 100
            if fill:
                self.fb.fill_rect(W - 17, 2, fill, 6, 1)
            label, right = "%d%%" % pct, W - 21
        lw = bitfont.width(font_oled_small, label)
        self.text(font_oled_small, right - lw, 0, label)
        room = right - lw - 4 - 18
        while bitfont.width(font_oled_small, net) > room and len(net) > 4:
            net = net[:-2] + "~"   # shorten a long network name
        self.text(font_oled_small, 18, 0, net)
        self.fb.hline(0, BAR_RULE, W, 1)

    def _dots(self, idx, count):
        gap = min(10, (W - 8) // max(count - 1, 1))
        x0 = W // 2 - (count - 1) * gap // 2
        for i in range(count):
            x = x0 + i * gap
            if i == idx:
                self.fb.fill_rect(x - 2, 58, 5, 5, 1)
            else:
                self.fb.fill_rect(x - 1, 59, 3, 3, 1)

    def render(self, name, menu, idx, count):
        self.fb.fill(0)
        self._status_bar()
        if menu:
            self._dots(idx, count)
        mid = (BAR_RULE + 1 + (DOTS_TOP if menu else H)) // 2
        font = NAME_FONTS[-1]
        for f in NAME_FONTS:
            if bitfont.width(f, name) <= W - 2:
                font = f
                break
        words = name.split()
        if font is NAME_FONTS[-1] and len(words) == 2:
            self.centered(font_oled_big, mid - 10, words[0])
            self.centered(font_oled_big, mid + 10, words[1])
        else:
            self.centered(font, mid, name)

    # --- Game of Life -----------------------------------------------------
    def _life_seed(self):
        noise = os.urandom(_LIFE_CELLS)
        for i in range(_LIFE_CELLS):
            self._life[i] = 1 if noise[i] < LIFE_DENSITY else 0
        self._life_gen = 0
        self._life_limit = 1
        self._life_mark = -1

    def life_advance(self):
        """One generation; a new soup once the old one dies or starts repeating."""
        if self._life_at is None:
            self._life_seed()
        else:
            _life_step(self._life, self._life_next)
            self._life, self._life_next = self._life_next, self._life
            h = _life_hash(self._life)
            if h == self._life_mark or h == 0:
                self._life_seed()
            else:
                self._life_gen += 1
                if self._life_gen >= self._life_limit:
                    self._life_mark = h
                    self._life_limit *= 2
        self._life_at = time.ticks_ms()
        _life_draw(self._life, self.buf)

    def _sleep_tick(self):
        """Called from the battery-mode sleep loop (the tasks aren't running)."""
        if self._in_life and self.i2c is not None:
            try:
                self.life_advance()
                self.show()
            except OSError:
                pass   # the run() task notices when it next wakes

    # --- task -----------------------------------------------------------
    async def run(self, switcher):
        from lib.power import power
        power.idle_tick = self._sleep_tick
        while True:
            if self.i2c is None:
                if not self.find():
                    await aio.sleep(RETRY_S)
                    continue
            await aio.sleep_ms(100)
            try:
                now = time.ticks_ms()
                if self._status_at is None or time.ticks_diff(now, self._status_at) >= STATUS_EVERY_MS:
                    self._status = self._read_status()
                    self._status_at = now
                menu = switcher.selecting_mode
                idx = switcher.selection_idx if menu else switcher.active_idx
                apps = switcher.apps
                name = apps[idx].name if apps else "no apps"
                page = (menu, idx, name)
                if page != self._page:
                    self._page, self._page_at = page, now
                if not menu and time.ticks_diff(now, self._page_at) >= LIFE_AFTER_MS:
                    self._in_life = True
                    self._last = None   # draw the name again when Life ends
                    if self._life_at is None or time.ticks_diff(now, self._life_at) >= LIFE_MS:
                        self.life_advance()
                        self.show()
                        if not self.on:
                            self.power(True)
                    continue
                self._in_life = False
                key = (menu, idx, name, self._status)
                if key != self._last or not self.on:
                    self.render(name, menu, idx, len(apps))
                    self.show()
                    if not self.on:
                        self.power(True)
                    self._last = key
            except OSError as ex:  # unplugged or bus glitch: look again later
                print("oled: lost:", repr(ex))
                self.i2c = None
                self.on = False
                await aio.sleep(RETRY_S)


oled = Oled()
