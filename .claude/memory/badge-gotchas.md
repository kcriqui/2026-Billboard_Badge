---
name: badge-gotchas
description: Badge failure modes found the hard way — LVGL re-init hang, USB freezes, requests crash, lost file writes
metadata:
  type: project
---

- **LVGL twice = hang.** A soft reset followed by importing `lib.epd` (which
  calls `lvgl.display_create` again) hangs the badge. Only RESET recovers.
  Never `mpremote run`/`exec` display code after a soft reset; hard-reset first
  or use `resume`. PR #4 added an `lvgl.deinit()` guard (the badge's LVGL has
  `is_initialized`/`deinit`), but whether it cures the hang is untested.
- **USB freezes, badge keeps running.** Several times the USB serial link died
  ("broken pipe" / I/O error on the port) while apps and buttons kept working.
  Only RESET (or replug) fixes it. Cause not pinned down; not caused by our
  apps. If the port stops answering, ask Kevin to press RESET rather than retry.
- **`requests` crashes the badge** (hard reboot) reading image bodies
  (`r.content`) from imgs.xkcd.com. Raw `socket` + `ssl.wrap_socket` with a
  Content-Length-sized buffer works fine; the XKCD app uses its own client.
- **Unclosed file writes are lost on reset.** `open(...).write(...)` without
  closing may leave the file empty after a reset; always use `with open(...)`.
- **Interrupting main.py leaves its asyncio tasks queued.** A later
  `asyncio.run()` from the REPL restarts them (two display loops at once →
  garbled panel). Call `asyncio.new_event_loop()` first in REPL test scripts.
  A dropped task never runs its `finally:` — so don't toggle shared flags
  around awaits (PR #4 did this with `_reverse_fb_bits`; we removed it after
  it left images bit-mirrored).
- **Light sleep vs USB and pins.** `machine.lightsleep()` breaks the USB
  serial link until a reset (on battery that's irrelevant; plugging USB in
  after battery use may need RESET). Pin wake doesn't work for the buttons:
  only RTC pins (GPIO 0-21) can wake (User A/Menu - are 39/40), only one
  `Pin.irq(wake=)` slot exists ("no resources"), button pull-ups drop out in
  sleep (instant false wakes), and `hold=True` on the pins hung the chip.
  Hence timer-only polling sleep. Test over USB by having the test write to
  flash and `machine.reset()` at the end, then read the file.
- **mpremote auto-connect** may pick the Feather — always pass the badge port.
- WiFi SSIDs are case-sensitive on the ESP32 (con network is `Supercon`);
  `lib/wifi.py` matches case-insensitively to avoid this trap.

- **OSError 116 (timeout) on some WiFi while small requests work** (ACCD
  venue WiFi, -77 dBm, 2026-11-07): TCP connects and tiny replies arrived,
  but anything over ~1 packet stalled, even plain HTTP; the laptop on the
  same network was fine and WiFi power-save made no difference. Fix: the
  badge now joins in 802.11b/g only (`lib/wifi.py`, `protocol=MODE_11B|MODE_11G`).
  If downloads stall somewhere new, check that first.

- **Fast refresh doesn't darken lone single pixels** (WOPR's 1-px dotted
  paths came out pale grey or invisible, 2026-11-07). Use 2x2 dots or
  thicker for anything that must show after a fast black-only refresh.
