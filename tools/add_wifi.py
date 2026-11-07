#!/usr/bin/env python3
"""Add WiFi networks this laptop already knows to the badge's wifi.json.

Run it yourself in a terminal (it reads saved passwords from NetworkManager,
so they go straight from there into the file and are never printed):

    python3 tools/add_wifi.py            # pick from a numbered list
    python3 tools/add_wifi.py "Home" "Mom's WiFi"   # by connection name

It merges into firmware/badge/data/wifi.json (gitignored, kept mode 600):
existing entries stay, an entry with the same SSID is replaced. Then push
(USB: cd firmware && ./dev.sh push, or WiFi: ./dev.sh ota) to send it to the
badge. If NetworkManager won't reveal a password, it asks you to type it.
"""

import getpass
import json
import os
import pathlib
import subprocess
import sys

WIFI_JSON = pathlib.Path(__file__).resolve().parent.parent / "firmware/badge/data/wifi.json"


def nm(*args):
    return subprocess.run(["nmcli", *args], capture_output=True, text=True).stdout


def saved_wifi():
    rows = []
    for line in nm("-t", "-f", "NAME,TYPE", "connection", "show").splitlines():
        name, _, kind = line.rpartition(":")
        if kind == "802-11-wireless":
            rows.append(name.replace("\\:", ":"))
    return rows


def details(conn):
    out = nm("-s", "-g", "802-11-wireless.ssid,802-11-wireless-security.key-mgmt,"
             "802-11-wireless-security.psk", "connection", "show", "id", conn)
    ssid, keymgmt, psk = (out.rstrip("\n").split("\n") + ["", "", ""])[:3]
    return ssid, keymgmt, psk


def main():
    conns = saved_wifi()
    picks = sys.argv[1:]
    if not picks:
        for i, c in enumerate(conns, 1):
            print(f"{i:3d}  {c}")
        ans = input("Numbers to add (e.g. 3 7): ").split()
        picks = [conns[int(a) - 1] for a in ans]
    try:
        current = json.loads(WIFI_JSON.read_text())
    except (OSError, ValueError):
        current = []
    if isinstance(current, dict):
        current = [current]
    for conn in picks:
        if conn not in conns:
            print(f"No saved WiFi connection called {conn!r}; skipped.")
            continue
        ssid, keymgmt, psk = details(conn)
        if keymgmt in ("", "none", "owe"):
            psk = ""          # open network
        elif keymgmt != "wpa-psk" and keymgmt != "sae":
            print(f"{conn}: {keymgmt} (enterprise) isn't supported by the badge; skipped.")
            continue
        elif not psk:
            psk = getpass.getpass(f"NetworkManager didn't reveal the password for {ssid!r}; type it: ")
        current = [n for n in current if n.get("ssid", "").lower() != ssid.lower()]
        current.append({"ssid": ssid, "password": psk})
        print(f"Added {ssid}")
    fd = os.open(WIFI_JSON, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(current, f)
    os.chmod(WIFI_JSON, 0o600)
    print(f"{WIFI_JSON} now has: " + ", ".join(n["ssid"] for n in current))


if __name__ == "__main__":
    main()
