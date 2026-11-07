---
name: badge-dev-workflow
description: How to deploy code to the badge, inspect it safely over USB, and test on the laptop first
metadata:
  type: reference
---

- Badge port: `/dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_7c4fad28cf74cb3f-if00`
  (USB 303a:4001). The ttyACM number changes (seen as ACM0 and ACM1 on
  2026-11-07), so always use the by-id path. A Feather (USB-JTAG
  303a:1001) is often plugged in too — never target it by accident.
- If the badge vanishes from USB (no /dev/serial/by-id entry), it's
  unplugged or in battery-mode light sleep: ask Kevin to plug in / press
  RESET.
- Laptop gotcha: `pkill -f <pattern>` also kills the shell running it when
  the pattern is in its own command line; kill by PID instead.
- Deploy: `cd firmware && ./dev.sh push` (copies only changed files from
  `badge/`, resets, shows output). `dev.sh` auto-picks the badge port.
  `scripts/update.py` takes `--port`/`$BADGE_PORT` and never overwrites
  `/data/panel_config.json` (boot counter / splash).
- WiFi networks: `firmware/badge/data/wifi.json` on the laptop is the master
  (push overwrites the badge's copy). It holds a list; the badge tries the
  ones in range. `python3 tools/add_wifi.py [conn names]` merges networks
  saved in NetworkManager without printing passwords. 2026-11-06: Kevin
  OK'd taking them from the laptop, then trimmed the list himself (7 networks
  on 2026-11-07, incl. ACCD he added by hand). Don't re-add ones he removed.
  Validate the JSON before pushing: a hand edit once left an entry after the
  closing `]`, which would have stopped WiFi entirely.
- No OTA: Kevin tried WiFi push and GitHub-pull OTA (2026-11-06) and chose
  USB-only updates. Don't re-propose OTA.
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
- Laptop previews run the badge's own code under CPython with stubs:
  `micropython.viper` → identity, `ptr8` → the buffer, `ptr16`/`ptr32` →
  the array itself or `memoryview(b).cast("H"/"I")`, `deflate` → zlib; then
  render the framebuffers with Pillow (fit_png, plasma, bitfont all work).
- **Shared checkout:** another Claude session may edit this repo at the same
  time (2026-11-06: the bitmap-font work). Stage files by name, never
  `git add -A`; `./dev.sh push` syncs *everything* in `firmware/badge/`,
  including others' uncommitted work, so check `git status` first and
  coordinate via cross-session messages.
- Editor: Pylance uses `pyrightconfig.json` + stubs in `typings/`
  (not committed; reinstall with `./dev.sh stubs`).
- `firmware/badge-backup/` (not committed) has the badge's original data files.
