---
name: badge-gotchas
description: Badge failure modes found the hard way — LVGL re-init hang, USB freezes, requests crash, lost file writes
metadata:
  type: project
---

- **LVGL twice = hang.** A soft reset followed by importing `lib.epd` (which
  calls `lvgl.display_create` again) hangs the badge. Only RESET recovers.
  Never `mpremote run`/`exec` display code after a soft reset; hard-reset first
  or use `resume`.
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
- **mpremote auto-connect** may pick the Feather — always pass the badge port.
- WiFi SSIDs are case-sensitive on the ESP32 (con network is `Supercon`);
  `lib/wifi.py` matches case-insensitively to avoid this trap.
