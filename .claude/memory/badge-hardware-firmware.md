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
- Crisp text: prefer `lib/bitfont.py` + 1-bit fonts over LVGL fonts (which
  are anti-aliased and look uneven once thresholded). Fonts: `font_small`
  (DejaVu Sans 12), `font_alt` (18, XKCD alt text — Kevin asked for bigger
  than 15), `font_big` (Bold 24). Make more with `tools/make_bitmap_font.py`.
  Draws into the black framebuffer only; keeps a 1/16 px pen for even spacing.
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
- Power: Kevin's badge has a single-cell LiPo on the pads (MCP73831 charger).
  Input-voltage sense (`lib/board.reg_in_v_sns`, x2 divider) reads ~4.6-4.7 V
  on USB, <= 4.2 V on battery.
- Battery mode (`lib/power.py`, started in main.py), for any app: on battery
  (< 4.45 V, or `/data/battery_mode` exists) and idle 15 s after a refresh →
  WiFi off, LEDs dark, light sleep in 150 ms steps reading all 4 buttons
  between; 300 ms awake every 20 s so timer apps run (faint blue blink on
  LED 0). A press longer than ~0.15 s wakes it and acts normally. Logs volts
  and sleep totals to `/data/power.log` every 10 min. Kevin tested it forced
  over USB 2026-11-06: works. Battery life not yet measured.
- Menu order (LED #, read from the badge 2026-11-07, after Earth became
  WOPR): 0 Gallery, 1 Nametag, 2 Space Weather, 3 WOPR, 4 XKCD (the OLED
  shows the names). `/data/app_list` keeps stale entries past the
  real count (never truncated); nothing reads it. It follows
  discovery order, not names; re-check with `switcher.apps` rather than
  assuming; `/data/last_app` (app name) reopens an app without the menu.
