"""Menu helper on an SSD1306 128x64 OLED (Adafruit #326) on the SAO I2C bus.

In the menu (Menu +/-) it shows the selected app's name between < > arrows,
"MENU n / N" above and a status line below (WiFi network + signal, battery
or USB). With the menu closed it shows the running app's name and the
status line. Layout B, chosen by Kevin from previews (tools/preview_oled.py).

Kevin's panel has a cracked corner: odd rows 1-21 and rows 59, 61, 63 are
dead, so the name and status stay in rows 22-58; the small "MENU" label in
the top strip shows combed but readable.

Off while battery mode sleeps (lib/power.py), back on at the next press.
If no OLED answers, the task waits and looks again every RETRY_S, so the
badge works the same without one.

Wiring: SAO pin 1 3V3, 2 GND, 3 SDA (GPIO17), 4 SCL (GPIO18). Kevin's
wires were crossed, so if nothing answers on the standard pins it tries
SDA/SCL swapped (bit-banged).
"""

import asyncio as aio
import time

import framebuf
from machine import I2C, Pin, SoftI2C

from lib import bitfont, font_oled_big, font_oled_mid, font_oled_small, wifi

ADDR = 0x3D
W, H = 128, 64
FLIP = False            # True if the OLED is mounted upside down
STATUS_EVERY_MS = 10000
RETRY_S = 30
NAME_Y = 34             # centre rows of the three lines (rows 22-58 are good)
STATUS_Y = 51
LABEL_Y = 1

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


class Oled:
    def __init__(self):
        self.i2c = None
        self.on = False
        self.buf = bytearray(W * H // 8)
        self.fb = framebuf.FrameBuffer(self.buf, W, H, framebuf.MONO_VLSB)
        self._last = None
        self._status = ""
        self._status_at = None

    # --- hardware -------------------------------------------------------
    def find(self):
        """Look for the OLED; True if found (and initialised)."""
        try:
            i2c = I2C(0, scl=Pin(18), sda=Pin(17), freq=400000)
            if ADDR in i2c.scan():
                self.i2c = i2c
            else:
                i2c = SoftI2C(scl=Pin(17), sda=Pin(18), freq=400000)
                if ADDR in i2c.scan():
                    print("oled: found with SDA/SCL swapped")
                    self.i2c = i2c
        except OSError:
            self.i2c = None
        if self.i2c is None:
            return False
        self._cmd(0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14,
                  0x20, 0x00, 0xA0 if FLIP else 0xA1, 0xC0 if FLIP else 0xC8,
                  0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6)
        self.on = False
        self._last = None
        print("oled: ready at 0x%02X" % ADDR)
        return True

    def _cmd(self, *cmds):
        for c in cmds:
            self.i2c.writeto(ADDR, bytes((0x80, c)))

    def show(self):
        self._cmd(0x21, 0, W - 1, 0x22, 0, H // 8 - 1)
        self.i2c.writeto(ADDR, b"\x40" + self.buf)

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

    def _status_line(self):
        from lib import power as power_mod
        if wifi.is_connected():
            try:
                net = "%s %ddBm" % (wifi._wlan.config("ssid"), wifi._wlan.status("rssi"))
            except Exception:
                net = "WiFi on"
        else:
            net = "no WiFi"
        batt = "%d%%" % battery_pct(power_mod.input_volts()) if power_mod.on_battery() else "USB"
        line = net + "   " + batt
        while bitfont.width(font_oled_small, line) > W and len(net) > 4:
            net = net[:-2] + "~"   # shorten a long network name
            line = net + "   " + batt
        return line

    def render(self, name, menu, idx, count):
        self.fb.fill(0)
        if menu:
            self.centered(font_oled_small, LABEL_Y + font_oled_small.HEIGHT // 2,
                          "MENU  %d / %d" % (idx + 1, count))
            arrow_w = bitfont.width(font_oled_small, ">") + 3
            self.text(font_oled_small, 0, NAME_Y - font_oled_small.HEIGHT // 2, "<")
            self.text(font_oled_small, W - arrow_w + 3, NAME_Y - font_oled_small.HEIGHT // 2, ">")
            x0, x1 = arrow_w, W - arrow_w
        else:
            x0, x1 = 0, W
        font = font_oled_big
        if bitfont.width(font, name) > x1 - x0:
            font = font_oled_mid
        self.centered(font, NAME_Y, name, x0, x1)
        self.centered(font_oled_small, STATUS_Y, self._status)

    # --- task -----------------------------------------------------------
    async def run(self, switcher):
        from lib.power import power
        while True:
            if self.i2c is None:
                if not self.find():
                    await aio.sleep(RETRY_S)
                    continue
            await aio.sleep_ms(100)
            try:
                if power.sleeping:
                    if self.on:
                        self.power(False)
                    continue
                now = time.ticks_ms()
                if self._status_at is None or time.ticks_diff(now, self._status_at) >= STATUS_EVERY_MS:
                    self._status = self._status_line()
                    self._status_at = now
                menu = switcher.selecting_mode
                idx = switcher.selection_idx if menu else switcher.active_idx
                apps = switcher.apps
                name = apps[idx].name if apps else "no apps"
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
