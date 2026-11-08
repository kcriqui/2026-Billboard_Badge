---
name: oled
description: 128x64 OLED on the SAO I2C bus for menu names and status - MachineIdeas SAO OLED at 0x3C, replaced the broken Adafruit #326
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
  previews `tools/preview_oled.py`. First layout (superseded below): "MENU n / N" in
  the top strip, "< Name >" (18 px, 14 px if too wide), status line
  "SSID -77dBm   78%" or "USB". Menu closed: running app's name + status.
  Off while battery mode sleeps. Game of Life idle screen: Kevin said
  "hold off for now".
- **Panel replaced 2026-11-08:** the #326 broke; now a MachineIdeas "SAO
  OLED" plugged straight into a SAO port, 128x64, at 0x3C (board option
  0x3C or 0x3D), standard pins, no dead rows. Status byte 0x45, controller
  not identified, but the SSD1306 init draws a clean full frame with no
  column offset. Driver tries both addresses, uses hardware I2C at 400 kHz
  (40/40 page writes passed) and page addressing. It first gave no I2C
  reply on either pin order until Kevin fixed the SAO connection; a write
  with no scan before it once gave ENODEV. The swapped-pins fallback and
  the layout limits for the old panel's dead rows are gone.
- **Full-display layout (Kevin, 2026-11-08, option B of previews):** status
  bar on top (signal bars, SSID, battery icon + % or USB) over a rule; name
  as large as fits (`font_oled_huge` 30, `_large` 24, `_big` 18, `_mid` 14),
  two-word names too long for 14+ wrap to two lines at 18; position dots at
  the bottom in the menu. `tools/preview_oled.py` runs the real render code.
- Phone photos of the OLED cut off rows (scan vs shutter): use Live Photo
  -> Long Exposure.
- Kevin can mount it upside down: SSD1306 0xA0/0xC0 flips 180 deg for free.
