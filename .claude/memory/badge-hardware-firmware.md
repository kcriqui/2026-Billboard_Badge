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
- Display refresh in MicroPython is the panel's slow full waveform only:
  ~30-40 s per update. Fast (~3.5 s, black/white) refresh exists only in the
  PlatformIO driver `firmware/esp32s3-itc97/`; `badge/data/rendered_luts.py`
  holds converted fast LUTs that nothing uses. Porting fast refresh to
  MicroPython was offered and declined for now (2026-11-06).
- Buttons: the Menu +/- silkscreen labels are swapped (noted in lib/button.py).
- LED bar: during every panel refresh `lib/epd.py` shows an amber progress
  bar (filling over the measured refresh time) then a green flash, via
  `leds.show_overlay()`/`clear_overlay()` in `lib/led_bar.py`. All LED writes
  go through `LedBar._out()`, so the overlay wins over app/menu LEDs and
  theirs reappear afterwards — don't call the NeoPixel `write()` directly.
- Power: single-cell LiPo pads + MCP73831 charger on the back. Whether Kevin's
  badge has a battery fitted is unknown; battery life with WiFi left on is
  untested. Without a battery, unplugging USB restarts the badge.
- Menu order is alphabetical by app file, and Schedule contributes 3 apps:
  Workshops, Sat Talks, Sun Talks, Gallery, Hello, Nametag, XKCD.
