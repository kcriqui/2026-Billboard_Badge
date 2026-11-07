---
name: badge-dev-workflow
description: How to deploy code to the badge, inspect it safely over USB, and test on the laptop first
metadata:
  type: reference
---

- Badge port: `/dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_7c4fad28cf74cb3f-if00`
  (USB 303a:4001, usually ttyACM0). A Feather (USB-JTAG 303a:1001, ttyACM1) is
  often plugged in too — never target it by accident.
- Deploy: `cd firmware && ./dev.sh push` (copies only changed files from
  `badge/`, resets, shows output). `dev.sh` auto-picks the badge port.
  `scripts/update.py` takes `--port`/`$BADGE_PORT` and never overwrites
  `/data/panel_config.json` (boot counter / splash).
- After any `mpremote` command that soft-resets (cp, exec without `resume`),
  do a hard `mpremote reset` before anything imports `lib.epd` — see
  [[badge-gotchas]].
- Inspect a running badge without breaking it: `mpremote connect $P resume exec "..."`
  (interrupts main.py but keeps LVGL state), then `mpremote reset` to restart.
  Test scripts that `asyncio.run()` must call `asyncio.new_event_loop()`
  first ([[badge-gotchas]]). Wait for any refresh to finish before interrupting.
- Battery mode can't be tested over USB without forcing it: create
  `/data/battery_mode`, reset, let Kevin test; to undo, have Kevin press RESET
  and remove the file within ~45 s (before it idles to sleep).
- Prefer having Kevin press buttons over driving apps via the REPL; read
  results afterwards from log files on flash (e.g. `/data/xkcd.log`).
- Compile-check viper code: `mpy-cross -march=xtensawin -o /dev/null file.py`.
- Laptop preview of image conversion: run `lib/fit_png.py` under CPython with
  stubs for `micropython.viper`, `ptr8`, `ptr32` (memoryview cast "I") and
  `deflate` (zlib), then render the framebuffers with Pillow.
- Editor: Pylance uses `pyrightconfig.json` + stubs in `typings/`
  (not committed; reinstall with `./dev.sh stubs`).
- `firmware/badge-backup/` (not committed) has the badge's original data files.
