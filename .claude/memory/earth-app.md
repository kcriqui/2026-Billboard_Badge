---
name: earth-app
description: WOPR app (was Long Exposure Earth) — WarGames-style war room with made-up missile tracks, world/polar boards, ISS + quakes, ghosting design, attribution
metadata:
  type: project
---

**2026-11-07: renamed WOPR** (`apps/wopr.py`, menu name "WOPR"; Kevin: "call
the app WOPR and remove the word simulation"). An homage to the WarGames
war-room screens (reference: hp9845.net WarGames gallery, 35 frames: polar
map with rings/spokes, USSR in red, streak bundles over the pole, dashed
arcs on the world screen, thin vector banners, numbered tracks, status
codes). Two boards alternate every 10 min (full refresh on switch): WORLD
(dashed arcs, big "MISSILE WARNING"/"LAUNCH DETECTION" banner in
`font_thin`) and POLAR (`data/earth/polar.png` from
`tools/make_world_map.py --projection polar`, POLAR_* constants shared;
streak bundles, track list). User A switches board at once (press
remembered while the panel is busy); User B launches a big salvo at the US now. When a US salvo has landed
(+1 update of blasts) the board clears and the lesson WOPR learned in the
film (12-word quote, Kevin's request) appears black-on-white in a panel
over the map with the quick refresh (Kevin: not a full-screen flash);
`font_mono_huge` (DejaVu Sans Mono Bold 46). B to lesson takes ~30-40 min. Missiles are made up, stored as city-to-city
flights so tracks carry on across view changes; labels sit at launch points
(moving labels smeared). Heads are rotated missile shapes; a faint dotted
path runs from each head to a dotted circle at its target.
`tools/preview_wopr_app.py` renders the app's real drawing code on the
laptop (framebuf stand-in) - use it for WOPR layout checks. DEFCON = missiles in flight to US cities (Kevin); 1 only when >=3 US-bound
missiles are within 2 updates of impact (big salvos share a flight time,
+-1, so they arrive together);
ordinary salvos avoid US cities, a big salvo (1 in 10, 4-8 missiles) spikes
it to 1-2; rising DEFCON forces a full refresh, falling waits. Simulated
over a day: DEFCON 5 ~58 % of the time. Fonts `font_mono`, `font_mono_big`,
`font_thin`; layout previews `tools/preview_earth_wopr.py`. Next idea:
one side in red needs Natural Earth admin-0 countries (~0.8 MB; ask first).

Original Long Exposure Earth (2026-11-06; Kevin: "looks good"):

- Every 3 min: ISS position (wheretheiss.at, ~300 B) → dot; only the last
  orbit (31 dots) is drawn black, older ones are left out so the panel's
  fast-refresh **ghosting** fades them (the "long exposure" idea). Quakes:
  USGS `2.5_day.geojson` (~22 KB) every 15 min, rings sized by magnitude,
  double ring for M6+.
- Refresh: fast with `keep_red=True` (red coastlines untouched); full on
  launch, hourly, on User B, and when a *new* M6+ quake appears (first feed
  load is a baseline). User A = update now.
- Map: `data/earth/world.png` 960x480 equirectangular, red coastlines
  (Kevin chose outlines over filled land: black marks stay readable and fade
  evenly). Decoded once, then copied from a RAM cache each frame.
- Marks clear red under them: black+red on one pixel = undriven table.
- Text (title, UTC time, footer) uses the 1-bit bitmap fonts (`lib/bitfont`,
  `font_big` / `font_small`), not LVGL — Kevin wants crisp fonts in all apps.
- **Attribution is required** (Kevin asked): Natural Earth credit in the app
  docstring, on-screen footer, tools/make_world_map.py and README credits.
  Raw `ne_110m_land.geojson` lives in gitignored `tools/data/` (download
  command in the tool's docstring).
- Not yet observed: how the real ghosting looks after an orbit of fast
  refreshes. Shares `lib/net.py` (HTTPS helper; XKCD still has its own copy).
- Next ideas Kevin liked: #2 space weather (built: [[spaceweather-app]]), #4 sky
  clock (moon/sun/planets computed on badge), mic seismograph after soldering.
