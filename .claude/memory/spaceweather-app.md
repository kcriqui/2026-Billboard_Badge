---
name: spaceweather-app
description: Space Weather app — full-screen dithered plasma (red/black/white) driven by NOAA solar wind data; layer/refresh design and what Kevin asked for
metadata:
  type: project
---

`apps/spaceweather.py` + `lib/plasma.py`, built 2026-11-06 (idea #2).

- Kevin's direction: **no solid colours at all** — the whole screen ordered-
  dithered in white/red/black with a *subtle* plasma effect. (A first try,
  black aurora curtains over a mountain silhouette, was dropped; the
  "curtains" version also read as V-shapes until flipped to rise from a
  lower edge — lesson: preview generative art early.)
- `lib/plasma.py`: sum of 4 sines from a 256-entry table, 8x8 Bayer
  thresholds, one viper call per row; a full 960x672 layer takes ~0.5 s on
  the badge (both layers ~1 s). Runs on the laptop with ptr8/ptr32 stubs, so
  previews are the badge's own output.
- Two layers: **red** (deep, slow; amount from Kp/storm) only redrawn with a
  full refresh — launch, every 5th update, storm-level change, User B — and cached;
  **black** (surface) redrawn every 3 min with fast `keep_red` refresh,
  skipping red pixels; waviness = southward Bz, density = Bt, drift per update
  = solar wind speed, so earlier frames ghost.
- Contrast: Kevin first asked for subtle, then "increase the contrast; some
  solid colour at the peaks is OK". Tones now sweep from < 0 (clean white
  troughs) to > 254 (solid peaks): calm ≈ 55 % white / 24 % red / 21 % black,
  storm ≈ 44 % red. Red offset -230 keeps calm red from swamping the black
  (black is never drawn over red). Tune in `plasma.from_weather`.
- **Red fades under fast refreshes** even with `keep_red` (Kevin saw it
  after a few updates). Not VCOM: in the driver-B fast LUT, VCOM (table 4)
  is ground throughout, so idle red pixels see no direct field. Likely cause:
  fringe fields from neighbouring dots being driven (white pixels get a
  0x99 shake, black a hard drive) disturb the isolated dithered red dots;
  3 pulses per update triple it. Fix in use (Kevin chose "A + test B"):
  full refresh after every `FAST_IN_A_ROW = 4` fast ones (~15 min) and
  `FAST_PASSES = 2` — "a little better". Then option C, Kevin's variant:
  red as **solid blobs with dithered fading rims** (red span 2200, lo
  -1330 + 20*Kp; calm ~21 % red, storm ~43 %); black/white stay dithered.
  Kevin: "better" — **OPEN, needs more attention later** (he asked to note
  it): red still fades somewhat between top-ups. Ideas not yet tried: 1
  pulse per fast refresh; narrower dithered rims (higher red span); keep
  black dots out of a margin around red; a custom fast LUT that leaves
  white pixels undriven (no 0x99 shake) — needs care, paper-white quality.
  Then relax the 15-min top-up if possible. WOPR's thin red coastlines may
  fade the same way (not checked).
- Preview/tune on the laptop: `python3 tools/preview_plasma.py` (badge code,
  live NOAA data + a storm + simulated ghosts, prints coverage).
- Update log on flash: `/data/spaceweather.log` (one line per update or
  failure; the only record while battery mode sleeps). A forced-battery test
  of whether updates keep running asleep was dropped (Kevin: "I think it's
  OK"); code review found nothing blocking.
- Small caption (bitmap `font_small`) with the numbers + "data: NOAA SWPC";
  User B toggles it (forces a full refresh). User A = update now.
- Feeds: `/products/summary/solar-wind-speed.json` and `-mag-field.json`
  (~60 B, a one-element list), `/json/planetary_k_index_1m.json` (~28 KB),
  `/products/noaa-scales.json` (G level). The old `/products/solar-wind/*`
  URLs 404; the rtsw 1-minute files are too big (300 KB+).
