---
name: earth-app
description: Long Exposure Earth app — ISS track + quakes on a red world map, designed around e-paper ghosting; data sources and attribution rules
metadata:
  type: project
---

`apps/earth.py` ("Earth"), built 2026-11-06; Kevin: "looks good".

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
- **Attribution is required** (Kevin asked): Natural Earth credit in the app
  docstring, on-screen footer, tools/make_world_map.py and README credits.
  Raw `ne_110m_land.geojson` lives in gitignored `tools/data/` (download
  command in the tool's docstring).
- Not yet observed: how the real ghosting looks after an orbit of fast
  refreshes. Shares `lib/net.py` (HTTPS helper; XKCD still has its own copy).
- Next ideas Kevin liked: #2 space weather (built: [[spaceweather-app]]), #4 sky
  clock (moon/sun/planets computed on badge), mic seismograph after soldering.
