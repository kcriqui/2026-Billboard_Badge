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
Hello (template example), XKCD ([[xkcd-app]]), handwritten Nametag
([[nametag]]); plus "reopen last app after restart" in the app switcher.

**How to apply:** work and commit in the fork; see [[badge-dev-workflow]] for
deploying and [[badge-gotchas]] before touching the display, USB or networking.
