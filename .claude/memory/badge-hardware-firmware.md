---
name: badge-hardware-firmware
description: Facts about the badge hardware and the MicroPython/LVGL firmware actually running on it (versions, fonts, refresh speed, power)
metadata:
  type: reference
---

- ESP32-S3, 8 MB PSRAM. 9.7" Pervasive Displays E2969JS0B1 ("B1") e-paper,
  960x672, white/black/red only. LED bar (WS2812) on GPIO38.
- Firmware on the badge: MicroPython 1.24.1 + LVGL 9.3, custom build
  ("Billboard Badge Generic ESP32S3"). `requests`, `ssl`, `deflate`, `network`
  are built in.
- LVGL fonts actually compiled in: montserrat 14, 16, 24, 28, 32, 36, 40, 44, 48.
  The repo's lv_conf.h lists more (e.g. 18) but they are NOT in the build.
- Full refresh = the panel's own (OTP) waveform, ~35 s of it physical.
  Measured 2026-11-06 (same image, before → after merging upstream PR #4,
  which uses hardware SPI + viper): LVGL 960x120 text 2657 → 105 ms,
  split/bit-reverse/SPI send ~5.3 s → ~0.4 s, panel waveform ~34.9 s both
  (physics), update() to done 44.5 → 36.5 s. PNG decode (large_png, 3-9 s,
  varies) is untouched by #4.
- Fast refresh (~5 s): `display.update(fast=True[, keep_red=True, passes=N])`,
  ported from upstream PR #3 (only its epd.py fast-refresh parts). Short waveform
  from `data/rendered_luts.py` written to 0xB0, re-triggered 3x on driver B.
  Black/white only (red goes pale), ghosting builds up. Kevin found it "fast
  and clean". Kill switch: create `/data/no_fast_refresh` on the badge (checked
  every update). Falls back to a full refresh if the LUT can't load.
- Buttons: the Menu +/- silkscreen labels are swapped (noted in lib/button.py).
- LED bar: during every panel refresh `lib/epd.py` shows an amber progress
  bar (filling over the measured refresh time) then a green flash, via
  `leds.show_overlay()`/`clear_overlay()` in `lib/led_bar.py`. All LED writes
  go through `LedBar._out()`, so the overlay wins over app/menu LEDs and
  theirs reappear afterwards — don't call the NeoPixel `write()` directly.
- Power: single-cell LiPo pads + MCP73831 charger on the back. Whether Kevin's
  badge has a battery fitted is unknown; battery life with WiFi left on is
  untested. Without a battery, unplugging USB restarts the badge.
- Menu order as seen on the badge (Schedule contributes 3 apps):
  Workshops, Sat Talks, Sun Talks, Gallery, Hello, Nametag, XKCD.
  It follows the order apps are discovered, not the names — check
  `switcher.apps` rather than assuming when adding apps.
