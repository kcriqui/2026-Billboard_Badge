---
name: xkcd-app
description: Design decisions behind the XKCD app (scaling, dithering rejected, WiFi file, logging, picking a comic) and why
metadata:
  type: project
---

Shows a random xkcd every 5 minutes; User A fetches one now. Works fully on
the badge (no laptop needed) on any WiFi in `wifi.json` that's in range.

- **Scaling is hybrid** (`lib/fit_png.py`): shrinking → area-average + bold
  threshold 200; enlarging (most comics) → cut at 170 (strong colours 128),
  then bilinear enlarge, cut at 150 ("F"). **Why:** dithering turned text into
  speckle (rejected; don't re-propose for line art); nearest-neighbour made
  tilted lines lumpy at odd scales like 1.28x; smoothing the gray original
  lost thin lines or filled bubble text. Kevin picked F over bicubic (D);
  F is also cheaper on the badge (2x2 vs 4x4 samples).
- Skips JPEGs (early comics), >1.5 MB files, and comics that would shrink
  below 60 %; comic 404 doesn't exist. Any comic fit_png can't decode
  (ValueError/MemoryError) is logged and skipped too, instead of an error
  screen. 16-bit PNGs are supported (high byte kept; e.g. #134).
- **Readability filter** (`fit_png.readability`, after drawing): skip if the
  median black stroke is < 3 px or >= 40 % of letter gaps are <= 3 px; up to
  3 tries, then show anyway; `xkcd_next` requests bypass it. Calibrated on 13
  comics Kevin judged at badge size: readable = 3-4 px strokes, <= 37 %;
  unreadable #581 (shrunk to 70 %) and #1688 (map) = 2 px. A plain
  "busyness" score did NOT separate them (#2553 readable at the same score as
  #1688). The log prints stroke/tight-gap for every comic, to retune.
- Own HTTPS client in `apps/xkcd.py` — see [[badge-gotchas]] (requests crash).
  Newer apps use the shared copy in `lib/net.py`; XKCD keeps its own because
  it raises SkipComic.
- WiFi credentials: `firmware/badge/data/wifi.json` (gitignored; a list of
  networks; see [[badge-dev-workflow]] for `tools/add_wifi.py`). Template:
  `wifi.json.example`.
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
- Layout: alt text in `font_alt` (bitfont), fully shown; the comic is fitted
  into the space left and placed right under the title (short comics move
  up, tall ones shrink), dropping alt lines only if the comic would go
  below MIN_SCALE.
- Timing on badge: download ~0.5-3 s, convert + readability ~1.3-1.9 s,
  LVGL text ~0.2 s, then
  the panel: ~36 s full (measured), ~5 s fast (Kevin confirmed on the badge,
  not instrumented). Buttons are unresponsive during download/convert.
- Possible follow-up: switch WiFi off between updates if battery life is poor.

Licence credit (2026-11-07): xkcd is CC BY-NC 2.5 (Randall Munroe). Header
reads "xkcd #N: Title" (LVGL, one line, ends "..." when too long) with a
two-line credit right-justified at the top right in font_small:
"xkcd.com/N" / "Randall Munroe, CC BY-NC 2.5" (Kevin picked this over a
one-line version from side-by-side previews). Settings `CREDIT`, `CREDIT_GAP`.
