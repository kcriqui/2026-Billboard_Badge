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

- Address 0x3D. No ssd1306 driver in the firmware; write our own small one
  (framebuf + init sequence; one that works is in the session test:
  0xAE,D5 80,A8 3F,D3 00,40,8D 14,20 00,A1,C8,DA 12,81 CF,D9 F1,DB 40,A4,A6,AF).
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
