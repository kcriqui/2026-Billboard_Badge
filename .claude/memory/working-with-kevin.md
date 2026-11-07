---
name: working-with-kevin
description: How Kevin likes to work on this project — visual comparisons before choices, testing on real hardware, pushing often
metadata:
  type: feedback
---

- Kevin uses he/him.
- For anything visual (image conversion, fonts, sizes), render options side
  by side on the laptop and let Kevin pick before deploying. **Why:** Kevin
  changed direction after seeing previews (dithering → hybrid scaling; font
  and size for the name tag). **How to apply:** put comparison PNGs in the
  session folder and send them.
- Kevin tests on the badge in person and reports what the screen shows;
  ask Kevin to press buttons/RESET rather than poking the badge over USB.
- Commit and push to the fork after each working step; never leave work only
  on the laptop.
- Software installs: apt/Flatpak first; give Kevin sudo commands to run.
  Ask before downloading anything (state file, source, size, licence).
- Credit third-party data, fonts and code: Kevin asked to "attribute our
  code to using it" (Natural Earth). Put credits in the app docstring, on
  screen where there's room, and in the README "Credits (Kevin's fork)".
- Kevin enjoys data-driven generative art that plays to e-paper quirks
  (ghosting, slow/fast refresh). He iterates on looks: expect "more
  contrast", "no solid colours" style follow-ups — keep tuning numbers in
  one place and preview at 100 % size.
