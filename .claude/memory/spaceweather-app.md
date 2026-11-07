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
  full refresh — launch, hourly, storm-level change, User B — and cached;
  **black** (surface) redrawn every 3 min with fast `keep_red` refresh,
  skipping red pixels; waviness = southward Bz, density = Bt, drift per update
  = solar wind speed, so earlier frames ghost.
- Contrast: Kevin first asked for subtle, then "increase the contrast; some
  solid colour at the peaks is OK". Tones now sweep from < 0 (clean white
  troughs) to > 254 (solid peaks): calm ≈ 55 % white / 24 % red / 21 % black,
  storm ≈ 44 % red. Red offset -230 keeps calm red from swamping the black
  (black is never drawn over red). Tune in `plasma.from_weather`.
- Small caption (bitmap `font_small`) with the numbers + "data: NOAA SWPC";
  User B toggles it (forces a full refresh). User A = update now.
- Feeds: `/products/summary/solar-wind-speed.json` and `-mag-field.json`
  (~60 B, a one-element list), `/json/planetary_k_index_1m.json` (~28 KB),
  `/products/noaa-scales.json` (G level). The old `/products/solar-wind/*`
  URLs 404; the rtsw 1-minute files are too big (300 KB+).
