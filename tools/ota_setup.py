#!/usr/bin/env python3
"""Make the OTA token for the badge (lib/ota.py) if there isn't one yet.

Writes firmware/badge/data/ota.json (gitignored, mode 600). Push once over
USB (cd firmware && ./dev.sh push) to install it; after that, with the badge
on any USB power and a known WiFi in range:  ./dev.sh ota
The token itself is never printed.
"""

import json
import os
import pathlib
import secrets

path = pathlib.Path(__file__).resolve().parent.parent / "firmware/badge/data/ota.json"
if path.exists():
    print(f"{path} already exists; keeping it.")
else:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"token": secrets.token_urlsafe(24)}, f)
    print(f"Wrote {path}. Push once over USB to install it on the badge.")
