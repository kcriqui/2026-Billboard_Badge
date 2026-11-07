---
name: oled
description: Adafruit #326 OLED on the SAO I2C bus for menu names/status/idle pattern - wiring, address, dead rows from the cracked corner
metadata:
  type: project
---

Kevin's OLED project (started 2026-11-07): an Adafruit #326 (0.96" 128x64,
SSD1306, STEMMA QT version: I2C by default, 3-5 V, auto-reset) on the SAO
I2C bus (all three SAO ports share SDA GPIO17 / SCL GPIO18; standard SAO
pinout 1 3V3, 2 GND, 3 SDA, 4 SCL). Goal: show the selected app's name in
the menu (no more LED counting), WiFi signal and battery; an idle pattern
(Game of Life) when the menu is closed; OLED off in battery-mode sleep.

- Built 2026-11-07: `lib/oled.py` (own SSD1306 driver + screens, started
  from main.py), fonts `lib/font_oled_{big,mid,small}.py` (DejaVu Sans
  Condensed Bold 18/14, regular 10, via tools/make_bitmap_font.py),
  previews `tools/preview_oled.py`. Kevin picked layout B: "MENU n / N" in
  the top strip, "< Name >" (18 px, 14 px if too wide), status line
  "SSID -77dBm   78%" or "USB". Menu closed: running app's name + status.
  Off while battery mode sleeps. Game of Life idle screen: Kevin said
  "hold off for now".
- Address 0x3D. Driver tries standard pins, then SDA/SCL swapped (SoftI2C).
- 2026-11-07 the SDA/SCL wires were found swapped (OLED answered only with
  SCL=17, SDA=18); Kevin was asked to swap blue/yellow. Re-scan before
  assuming either way.
- Kevin broke a glass corner. Dead rows (from a staircase test photo):
  odd rows 1-21 and rows 59, 61, 63. Rows 22-58 are all good. Every
  even/odd row pair has its even row alive, so anything drawn 2 px tall
  per logical row (2x2 Life cells, vertically doubled text) shows fully
  across the whole screen. Keep fine text in rows 22-58.
- Phone photos of the OLED cut off rows (scan vs shutter): use Live Photo
  -> Long Exposure.
- Kevin can mount it upside down: SSD1306 0xA0/0xC0 flips 180 deg for free.
