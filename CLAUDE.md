# 2026 Billboard Badge (Kevin's fork)

## Rules
- Work here (`~/dev/2026-Billboard_Badge`). Commit and push to `origin` (the fork) after each working step; `upstream` is Hack-a-Day — never push there.
- Deploy with `cd firmware && ./dev.sh push`. Confirm the target port before flashing or erasing; the badge is the `Espressif_Systems_Espressif_Device` port, not the USB-JTAG Feather.
- Never run display code after a soft reset (hangs the badge) — hard-reset first. If USB stops answering, ask Kevin to press RESET.
- Never commit `firmware/badge/data/wifi.json` or `tools/fonts/`; never handle the WiFi password.
- Show visual options as side-by-side previews and let Kevin choose before deploying.
- Installs: apt/Flatpak first (Kevin runs sudo). Ask before downloading files.
- Credit third-party data/fonts/code in the app and the README Credits section.
- Other sessions may share this checkout: stage files by name, check `git status` before `dev.sh push`.

## Memory (read as needed) — `.claude/memory/`
- [project-overview](.claude/memory/project-overview.md) — repos, remotes, what's built, upstream PR status
- [working-with-kevin](.claude/memory/working-with-kevin.md) — collaboration preferences
- [badge-hardware-firmware](.claude/memory/badge-hardware-firmware.md) — versions, fonts, refresh, power
- [badge-dev-workflow](.claude/memory/badge-dev-workflow.md) — port, deploy, safe inspection, laptop previews
- [badge-gotchas](.claude/memory/badge-gotchas.md) — known hangs/crashes and workarounds
- [xkcd-app](.claude/memory/xkcd-app.md) — XKCD app design decisions
- [nametag](.claude/memory/nametag.md) — name tag + photos, choices and regeneration
- [earth-app](.claude/memory/earth-app.md) — Long Exposure Earth design, data sources, attribution
- [spaceweather-app](.claude/memory/spaceweather-app.md) — dithered plasma driven by NOAA space weather

Keep these files current: update or delete stale facts rather than appending.
