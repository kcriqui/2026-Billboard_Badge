---
name: earth-app
description: WOPR app (was Long Exposure Earth) — WarGames-style war room with made-up missile tracks, world/polar boards, DEFCON, lesson screen, ISS + quakes, ghosting, attribution
metadata:
  type: project
---

`apps/wopr.py`, menu name "WOPR" (renamed from Long Exposure Earth on
2026-11-07; Kevin: "call the app WOPR and remove the word simulation" — no
"simulation" wording on screen). An homage to the WarGames war-room screens;
reference: hp9845.net WarGames gallery (35 frames: polar map with
rings/spokes, USSR in red, streak bundles over the pole, dashed arcs on the
world screen, thin vector banners, numbered tracks, status codes). Write the
screen text in our own words, except the lesson below.

**Boards** — alternate every 10 min (`VIEW_S`, full refresh on switch):
- WORLD: `data/earth/world.png`, dashed arcs, big banner ("LAUNCH
  DETECTION" / "MISSILE WARNING" / "TRACKING") in `font_thin`.
- POLAR: `data/earth/polar.png` from `tools/make_world_map.py --projection
  polar` (POLAR_* constants must match the app), streak bundles over the
  pole, track list (id + side) and ISS/quake panels. Reaches 20°S; track
  points past the rim are None and not drawn.
- Header "WOPR // STRATEGIC DISPLAY", status-code lines, DEFCON box top
  right (current level red with a white digit). Footer keeps the credits.

**Buttons:** User A = switch board now (press remembered while the panel is
busy); User B = big salvo at US cities now.

**Missiles (made up):** stored as city-to-city flights [launch step, flight
steps, from, to, id, lift], independent of the map, so tracks carry on across
board switches. Three sides: WEST (US + London/Paris), EAST (Moscow, Berlin,
China...), SOUTH (Johannesburg, Caracas, Sydney — Kevin); extra southern
targets Sao Paulo, Buenos Aires, Lima, Cape Town, Perth, Auckland. Ordinary
salvos (every 3 updates) hit non-US cities of other sides, north-south too
(Kevin OK'd). Big salvos (1 in 10, 4-8 missiles, EAST → US) share a flight
time ±1 so they arrive together. Salvos avoid repeating an in-flight pair.
Flights take 7-12 updates (3 min each). PREROLL starts mid-exchange.

**Drawing:** heads are rotated missile shapes; a faint dotted path (2x2
dots — sparse 1 px dots went pale in fast refreshes) from each head to a dotted target
circle; track id at the launch point (moving labels smeared). Impact =
mushroom cloud (Kevin, 2026-11-07), young 32 px on the 1st update, full
48 px on the 2nd, rising from the target: sprites in
`lib/sprite_mushroom.py` made by `tools/make_mushroom.py` (billows lit
like spheres, modelled on Wikipedia test-shot photos; Atkinson dither at
1 px — Kevin rejected 2x2 cells and the first, double size). Silhouette
cleared to white on both planes (framebuf.blit with a 1->0 palette), ink
on top. Then the track stops being drawn and ghosts away. World arcs peak high like the film: lift 0.5-0.8 × east-west distance
(full length made north-south routes hook back), peaks past the edge
squeezed into a band spread by lift; routes averaging south bow south. A
final pass clears red under all black (black + red = undriven pixel).

**DEFCON:** missiles in flight to US cities: 0→5, 1→4, 2-3→3, 4+→2; 1 only
when ≥3 are within 2 updates of impact. Rising DEFCON forces a full refresh
(red box); falling waits for the next scheduled one.

**Lesson:** when a US salvo has landed and both cloud stages have shown
(`BLAST_STEPS` updates; before 2026-11-07 it cut off the full cloud) the board
clears its tracks and shows the lesson WOPR learns in the film ("A STRANGE
GAME. / THE ONLY WINNING MOVE IS / NOT TO PLAY." — Kevin's request) in a
white panel over the map, black/white with the quick refresh (Kevin: not a
full-screen flash), `font_mono_huge`. B to lesson ≈ 30-45 min; Kevin chose to
keep that pace.

**Fonts:** `font_mono` (15), `font_mono_big` (Bold 26), `font_mono_huge`
(Bold 46), `font_thin` (ExtraLight 44 via `make_bitmap_font --stroke 2`:
centreline redrawn with a 2x2 pen; hinting gave 1/2 px and --dilate 2/3 px
strokes, Kevin saw both).

**Tools:** `tools/preview_wopr_app.py out.png [--salvo] [--steps N]
[--lesson]` runs the app's real drawing code on the laptop (framebuf
stand-in) — use it for layout checks. `tools/preview_earth_wopr.py` holds the
early layout sketches (approximate, not the app's code).

**Data & refresh (from Long Exposure Earth):** ISS (wheretheiss.at) every
3 min, last orbit (31 dots) drawn, older dots ghost away; USGS
`2.5_day.geojson` quakes every 15 min, rings by magnitude, double ring M6+.
Fast `keep_red` refresh between full ones (launch, switch, rising DEFCON,
new M6+ quake, hourly). Maps are decoded once and cached in RAM.

**Attribution is required** (Kevin): Natural Earth credit in the app
docstring, on-screen footer, tools/make_world_map.py and README credits
(which also note the WarGames homage and hp9845.net). Raw
`ne_110m_land.geojson` lives in gitignored `tools/data/` (download command
in the tool's docstring).

Ideas not done: one side's land in red needs Natural Earth admin-0
countries (~0.8 MB; ask before downloading).
