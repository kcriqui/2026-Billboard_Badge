---
name: nametag
description: Kevin's handwritten "Hello I am" name tag — chosen font/size and how to regenerate it
metadata:
  type: project
---

The Nametag app shows `data/graphics/hello_i_am_<name>.png` if present
(currently `hello_i_am_kevin.png`), else the blank tag + LVGL text.

Kevin's choices (2026-11-06): text "Kevin"; handwriting, not a plain sans;
xkcd Script, normal weight (not thickened); mixed case (all-caps Humor Sans and small-caps fakes
were rejected); 116 px tall ("larger"; 86 px was picked first, then
Kevin asked for bigger).

- Regenerate: `python3 tools/make_nametag.py Kevin [--height N] [--stroke N]`
  then `cd firmware && ./dev.sh push`. Delete old `hello_i_am_*.png` files when
  the name changes (the app takes the first alphabetically).
- Font file `tools/fonts/xkcd-script.ttf` is gitignored (CC BY-NC); the
  download command is in the tool's docstring. Other handwriting fonts are
  installed via apt: Humor Sans, Comic Neue, Purisa, Dancing Script.
- Images must be white/black/red only, no anti-aliasing, non-interlaced
  palette PNG — the tool does this.
