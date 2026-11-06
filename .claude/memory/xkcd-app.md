---
name: xkcd-app
description: Design decisions behind the XKCD app (scaling, dithering rejected, WiFi file, logging, picking a comic) and why
metadata:
  type: project
---

Shows a random xkcd every 5 minutes; User A fetches one now. Works fully on
the badge (no laptop needed) when the `Supercon` WiFi is in range.

- **Scaling is hybrid** (`lib/fit_png.py`): shrinking → area-average + bold
  threshold 200; enlarging (most comics) → nearest-neighbour, threshold 170,
  strong colours at 128. **Why:** Kevin asked for dithering; side-by-side
  previews showed Floyd-Steinberg/Atkinson turn text into speckle, and
  averaging fills white text inside black shapes when enlarging. Don't
  re-propose dithering for line art.
- Skips JPEGs (early comics), >1.5 MB files, and comics that would shrink
  below 60 % (unreadable); comic 404 doesn't exist.
- Own HTTPS client in `apps/xkcd.py` — see [[badge-gotchas]] (requests crash).
- WiFi credentials: `firmware/badge/data/wifi.json` (gitignored; Kevin writes
  it — never handle the password). Template: `wifi.json.example`.
- Debug log on flash: `/data/xkcd.log` (fresh per launch, capped at 8 KB).
- Show a specific comic next: write its number to `/data/xkcd_next` (with
  `with open`), it is used once and deleted.
- Refresh: full on app launch, when the comic or the previous one has red,
  and every 10th update (Kevin's choice; `FAST_IN_A_ROW = 9`); fast otherwise.
  `USE_FAST_REFRESH = False` in apps/xkcd.py turns it off.
- User B redraws the current comic with a full refresh (framebuffers still
  hold it). Side-by-side photos of #871 (2026-11-06): fast vs full look the
  same — fast blacks are, if anything, more neutral (full has a faint brown
  tint in solid areas); no visible ghosting after one fast update.
- Timing on badge: download ~0.5-3 s, convert ~1 s, LVGL text ~0.1 s, then the
  panel: ~36 s full (measured), ~5 s fast (Kevin confirmed on the badge, not instrumented). Buttons are unresponsive during download/convert.
- Possible follow-up: switch WiFi off between updates if battery life is poor.
