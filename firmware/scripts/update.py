#!/usr/bin/env python3

import argparse
import binascii
import hashlib
import os
import pathlib
import json
import subprocess
import urllib.parse
import urllib.request
from typing import Iterable

# Set by --port or $BADGE_PORT. With more than one board plugged in, plain
# "mpremote" connects to whichever it finds first, which may not be the badge.
MPREMOTE = ["mpremote"]

# Files the badge rewrites at runtime. push only creates them, never overwrites,
# so pushing code does not reset the boot counter and re-show the splash screen.
BADGE_STATE_FILES = {"/data/panel_config.json"}


def check_path(path: str, ) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    top_path = pathlib.Path(path)
    for file_path in top_path.iterdir():
        if file_path.is_file():
            with open(file_path, "rb") as file:
                hasher = hashlib.sha256(file.read())
                files[file_path.as_posix()] = hasher.digest()
        else:
            if file_path.name in ["__pycache__", ".git"]:
                continue
            files.update(check_path(str(file_path)))
            files[file_path.as_posix()] = b""
    return files

def check_dir(path: str) -> dict[str, str]:
    files_uncleaned = check_path(path)
    files = {fn.replace(path.strip() + "/", "/").replace("\\", "/"): binascii.hexlify(hash).decode() for fn, hash in files_uncleaned.items()}
    return files

def sort_paths_recursively(paths: Iterable[str]) -> list[str]:
    """Return paths sorted depth-first so parents appear before children."""
    return sorted(paths, key=lambda name: (name.count("/"), name))

def format_recursive_path(name: str) -> str:
    """Indent nested entries to make the hierarchy clearer."""
    depth = max(name.count("/") - 1, 0)
    return f"{'  ' * depth}{name}"

# --host: talk to the badge's OTA server (badge/lib/ota.py) over WiFi instead
# of USB. The token is the one in the gitignored badge/data/ota.json.
OTA_URL = None
OTA_TOKEN = ""


def _ota(method: str, route: str, path: str = "", body: bytes | None = None, timeout: float = 60) -> str:
    url = OTA_URL + route
    if path:
        url += "?p=" + urllib.parse.quote(path, safe="/")
    req = urllib.request.Request(url, data=body, method=method, headers={"X-Token": OTA_TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()


def badge_mkdir(name: str) -> None:
    if OTA_URL:
        _ota("PUT", "/dir", name)
    else:
        subprocess.run([*MPREMOTE, "mkdir", name], check=True)


def badge_put(name: str) -> None:
    if OTA_URL:
        with open(f"badge{name}", "rb") as f:
            _ota("PUT", "/file", name, f.read(), timeout=300)
    else:
        subprocess.run([*MPREMOTE, "cp", f"badge{name}", f":{name}"], check=True)


def badge_rm(name: str, is_dir: bool) -> None:
    if OTA_URL:
        _ota("DELETE", "/file", name)
    else:
        subprocess.run([*MPREMOTE, "rm", *(["-r"] if is_dir else []), name], check=True)


def badge_reset() -> None:
    if OTA_URL:
        _ota("POST", "/reset")
    else:
        subprocess.run([*MPREMOTE, "reset"], check=True)


def get_badge_files() -> dict[str, str]:
    if OTA_URL:
        files = {}
        for line in _ota("GET", "/files", timeout=180).splitlines():
            name, _, checksum = line.partition(" ")
            files[name] = checksum.strip()
        return files
    return _get_badge_files_usb()


def _get_badge_files_usb() -> dict[str, str]:
    """Get the files on the badge and their checksums."""
    badge_files_text = subprocess.run([*MPREMOTE, "run", "./scripts/check_filesystem.py"], capture_output=True, text=True).stdout
    badge_files = {}
    for line in badge_files_text.split("\n"):
        if " " in line:
            try:
                name, checksum = line.split(" ")
                badge_files[name] = checksum.strip()[2:-1]
            except ValueError as err:
                print(err)
                print(line)
    return badge_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser("Badge Updater")
    parser.add_argument("action", type=str, nargs="?", default="ls", help="Action to perform: 'ls' to list files (default), 'push' to push files, 'pull' to pull files.")
    parser.add_argument("--reset", action="store_true", default=False, help="Reset the badge after.")
    parser.add_argument("--verbose", "-v", action="store_true", default=False)
    parser.add_argument("--port", "-p", default=os.environ.get("BADGE_PORT"), help="Serial port of the badge (default: $BADGE_PORT, else mpremote's auto-detect).")
    parser.add_argument("--host", default=None, help="Update over WiFi via the badge's OTA server, e.g. kevin-badge.local or an IP (port 8266 unless given).")
    args = parser.parse_args()
    if args.host:
        host = args.host if ":" in args.host else args.host + ":8266"
        OTA_URL = "http://" + host
        try:
            with open("badge/data/ota.json") as f:
                OTA_TOKEN = json.load(f)["token"]
        except (OSError, KeyError, ValueError):
            print("No token in badge/data/ota.json - run tools/ota_setup.py, then push once over USB.")
            exit(1)
        if args.action == "pull":
            print("pull works over USB only.")
            exit(1)
    if args.port:
        MPREMOTE = ["mpremote", "connect", args.port]
    if args.action not in ("ls", "list", "push", "pull"):
        print(f"Unknown action '{args.action}'. Use 'ls', 'push', or 'pull'.")
        exit(1)

    if args.action == "push":
        print("Checking badge/ directory...")
        local_files = check_dir("badge")
        print("Checking files on badge...")
        badge_files = get_badge_files()
        for name in sorted(local_files.keys()):
            hash = local_files[name]
            if name not in badge_files and hash == "":
                print(f"Creating directory {name}...")
                badge_mkdir(name)
            elif name in BADGE_STATE_FILES and name in badge_files:
                if args.verbose:
                    print(f"{name} is badge state, leaving it alone.")
            elif name not in badge_files or badge_files[name] != hash:
                if name not in badge_files:
                    print(f"Creating {name}...")
                else:
                    print(f"Updating {name}...")
                badge_put(name)
            else:
                if args.verbose:
                    print(f"{name} is up to date.")
        files_to_delete = set(badge_files.keys()) - set(local_files.keys())
        for name in sorted(files_to_delete, reverse=True):
            if name.startswith("/data"):  # Don't delete the data/ directory.
                continue
            if "__pycache__" in name:  # Don't delete cache files
                continue
            if badge_files[name] == "":
                # Can't use rmdir because __pycache__ will linger
                print(f"Removing directory {name} from badge...")
                badge_rm(name, True)
            else:
                print(f"Deleting {name} from badge...")
                badge_rm(name, False)

    if args.action == "pull":
        print("Pulling files from badge...")
        badge_files = get_badge_files()
        if not os.path.exists("badge-backup"):
            os.makedirs("badge-backup")
        file_text = subprocess.run([*MPREMOTE, "cp", "-r", ":", "badge-backup/"], check=True)
        # for name in badge_files.keys():
        #     print(f"Pulling {name}...")
        #     with open(f"badge-backup/{name}", "w") as file:
        #         file.write(file_text)
        print("Files pulled successfully.")

    if args.action in ("ls", "list"):
        local_files = check_dir("badge")
        badge_files = get_badge_files()
        print("Files on badge:")
        print("Status values: * different, + only on local (push will add), - only on badge (push will delete)")
        print(f"Status {'Filename':<40s} SHA256")
        all_files = set(local_files.keys()).union(set(badge_files.keys()))
        for name in sort_paths_recursively(all_files):
            if name in local_files and name in badge_files:
                if local_files[name] == badge_files[name]:
                    status = " "
                else:
                    status = "*"
            elif name in badge_files:
                status = "-"
            elif name in local_files:
                status = "+"
            else:
                status = "?"
            hash = badge_files[name] if name in badge_files else local_files[name]
            if hash == "":
                hash = "directory"
            print(f"{status}      {format_recursive_path(name):<40s} {hash}")

    if args.reset:
        print("Resetting badge...")
        badge_reset()
