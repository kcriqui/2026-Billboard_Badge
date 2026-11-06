---
name: project-overview
description: What the Supercon 2026 badge project is, where its repos and files live, and its current state
metadata:
  type: project
---

Kevin is hacking the Hackaday Supercon 2026 "Billboard Badge" (work started
2026-11-06, at the con — the `Supercon` WiFi was in range) and wants to show
it off around the con.

- Code: `~/dev/2026-Billboard_Badge`, a fork. `origin` = kcriqui/2026-Billboard_Badge
  (push here), `upstream` = Hack-a-Day/2026-Billboard_Badge (pull updates:
  `git pull upstream main`). Upstream only has `main`.
- `~/dev/supercon-2026` (kcriqui/supercon-2026) is an empty placeholder repo
  made before the fork; nothing lives there.
- `/mnt/projects/Claude/Supercon 2026` (NAS) only holds preview/comparison PNGs
  from design decisions; it is not a repo.

Apps Kevin added (all on the badge and committed as of 2026-11-06):
Hello (template example), XKCD ([[xkcd-app]]), handwritten Nametag with
photos ([[nametag]]); plus "reopen last app after restart" in the app
switcher and an LED-bar refresh progress indicator for every app.

Upstream PR #4 (trandi, faster epd.py) is merged into the fork as a real
merge of its commit, with our changes on top: its LED-0 blinking removed in
favour of our progress bar, and its `_reverse_fb_bits` toggling replaced
(see [[badge-gotchas]]). When Hackaday merges #4 (or #3, which rewrites the
same file), expect conflicts in `lib/epd.py` around `run()`; keep the
progress bar hooks. No upstream PRs were merged as of 2026-11-06.

Parked: wiring a GY-MAX4466 microphone (Kevin will solder it later). Plan:
3.3 V + GND from an SAO port, OUT to an ADC1 pin (GPIO4/5 on SAO2 or the
GPIO9 pad; ADC2 is unusable with WiFi on). Favoured app: sound-reactive LED
bar + applause leaderboard on the e-paper. Calvin and Hobbes was ruled out
(no legitimate open source of strips).

**How to apply:** work and commit in the fork; see [[badge-dev-workflow]] for
deploying and [[badge-gotchas]] before touching the display, USB or networking.
