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

Apps Kevin added (all on the badge and committed as of 2026-11-06; the Hello
example and the stock Schedule app (Workshops/Sat/Sun Talks) were removed
2026-11-06):
XKCD with fast refresh ([[xkcd-app]]),
handwritten Nametag with two photos ([[nametag]]), WOPR (was Long Exposure Earth)
([[earth-app]]) and Space Weather ([[spaceweather-app]]). Shared pieces:
"reopen last app after restart" in the app switcher, an LED-bar refresh
progress indicator for every app, a battery mode that sleeps between updates
for any app, crisp 1-bit bitmap fonts (`lib/bitfont`, made in a parallel
session) and a shared HTTPS helper `lib/net.py` ([[badge-hardware-firmware]]).
**Open issue (Kevin, 2026-11-06): Space Weather's red fades between full
refreshes — improved, needs more attention later** ([[spaceweather-app]]).
Still to build from the ideas list: #4 sky clock (moon/sun/planets computed
on the badge), the mic seismograph once the mic is soldered, a QR code in
Nametag, "Now & Next" schedule, sharing apps via upstream `user_apps/`.

Upstream status (checked 2026-11-06 evening; 12 PRs open): Hackaday merged PR #10 (boot-42 easter-egg
fix), removed the PlatformIO drivers (`firmware/esp32s3-itc97*`), and added
`user_apps/` — share apps by PR as a subdirectory there; the best may be
baked into the firmware. All merged into the fork. Kevin's XKCD/Nametag
apps could be submitted there (not done; his call).

From open PRs, the fork carries: #4 (trandi, faster epd.py) as a real merge
of its commit, with its LED-0 blinking replaced by our progress bar and its
`_reverse_fb_bits` toggling removed ([[badge-gotchas]]); and only the
fast-refresh parts of #3 (FacioErgoSum), ported by hand. When Hackaday merges
#4 or #3, expect conflicts in `lib/epd.py` around `run()`/`global_update()`;
keep the progress bar and fast-refresh hooks.

Parked: wiring a GY-MAX4466 microphone (Kevin will solder it later). Plan:
3.3 V + GND from an SAO port, OUT to an ADC1 pin (GPIO4/5 on SAO2 or the
GPIO9 pad; ADC2 is unusable with WiFi on). Favoured app: sound-reactive LED
bar + applause leaderboard on the e-paper. Calvin and Hobbes was ruled out
(no legitimate open source of strips).

**How to apply:** work and commit in the fork; see [[badge-dev-workflow]] for
deploying and [[badge-gotchas]] before touching the display, USB or networking.
