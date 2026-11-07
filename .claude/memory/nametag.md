---
name: nametag
description: Kevin's Nametag app — handwritten "Hello I am" tag plus photos (incl. recursive one), choices and how to regenerate
metadata:
  type: project
---

The Nametag app cycles pictures with User A (next) / User B (previous):
first the name tag — `data/graphics/hello_i_am_<name>.png` if present
(currently `hello_i_am_kevin.png`), else the blank tag + LVGL text — then
every PNG in `data/photos/`. Kevin asked for photos here rather than a
separate Photo app (that app was removed).

Kevin's choices (2026-11-06): text "Kevin"; handwriting, not a plain sans;
xkcd Script, normal weight (not thickened); mixed case (all-caps Humor Sans
and small-caps fakes were rejected); 116 px tall ("larger"; 86 px was picked first, then
Kevin asked for bigger).

- Regenerate: `python3 tools/make_nametag.py Kevin [--height N] [--stroke N]`
  then `cd firmware && ./dev.sh push`. Delete old `hello_i_am_*.png` files when
  the name changes (the app takes the first alphabetically).
- Font file `tools/fonts/xkcd-script.ttf` is gitignored (CC BY-NC); the
  download command is in the tool's docstring. Other handwriting fonts are
  installed via apt: Humor Sans, Comic Neue, Purisa, Dancing Script.
- Photos: `python3 tools/make_photo.py <photo> <name> [--bw] [--centre x,y]`
  → `data/photos/<name>.png`. Kevin chose Atkinson dither with red
  (black/white/red) over Floyd-Steinberg, which washed out his face.
  `data/photos/kevin.png` is a laptop-webcam selfie wearing the badge;
  Kevin OK'd committing it to the public repo.
- `data/photos/kevin_recursive.png`: the same selfie with the photo composited
  into the badge's own screen 4 levels deep (`tools/make_recursive_photo.py`,
  then make_photo.py). Compositing beat retaking: a camera shot of dithered
  e-paper re-dithers into moiré. Kevin keeps both photos in the cycle.
- Laptop webcam: HP privacy mode makes it send a "camera off" icon until
  Kevin toggles the camera key. Capture with GStreamer (`v4l2src` →
  `jpegenc`/`multifilesink`; no ffmpeg installed), with a mirrored
  `autovideosink` preview window so Kevin can frame the shot.
- Images must be white/black/red only, no anti-aliasing, non-interlaced
  palette PNG — the tool does this.
