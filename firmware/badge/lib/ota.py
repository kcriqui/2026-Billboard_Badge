"""Over-the-air updates: a tiny HTTP file server for `./dev.sh ota`.

Runs as a background task (started in main.py) when /data/ota.json exists:
    {"token": "<random secret>"}
Every request must carry the header  X-Token: <token> ; without the file the
server never starts. tools/ota_setup.py makes the token on the laptop (in
the gitignored firmware/badge/data/ota.json) and one USB push installs it.

It listens only while the badge is on external power (USB, charger or
laptop): in battery mode WiFi is switched off between updates (lib/power.py).
On power it keeps WiFi joined (lib/wifi.py networks) and answers at
http://<HOSTNAME>.local:PORT or its IP (printed and in /data/ota.log).

Endpoints (paths are on-badge absolute paths, e.g. /apps/xkcd.py):
    GET    /files          one line per entry: "<path> <sha256 hex>",
                           directories have an empty hash
    PUT    /file?p=PATH    body = file contents (Content-Length required);
                           written to PATH.tmp, then renamed over PATH
    PUT    /dir?p=PATH     mkdir
    DELETE /file?p=PATH    remove a file, or a directory tree
    POST   /reset          reply, then machine.reset() (a hard reset: a soft
                           reset would hang the display)
"""

import asyncio as aio
import binascii
import hashlib
import json
import os
import time

import machine

from lib import wifi

PORT = 8266
TOKEN_PATH = "/data/ota.json"
LOG_PATH = "/data/ota.log"
RETRY_S = 60
MAX_BACKOFF_S = 15 * 60
CHUNK = 2048


def _token():
    try:
        with open(TOKEN_PATH) as f:
            tok = json.load(f).get("token", "")
        return tok if len(tok) >= 16 else None
    except (OSError, ValueError):
        return None


def _log(line):
    print("ota:", line)
    try:
        with open(LOG_PATH, "w") as f:  # last state only
            f.write("%d %s\n" % (time.time(), line))
    except OSError:
        pass


def _unquote(s):
    out = bytearray()
    i = 0
    while i < len(s):
        c = s[i]
        if c == "%" and i + 2 < len(s):
            out.append(int(s[i + 1:i + 3], 16))
            i += 3
        else:
            out.extend(c.encode())
            i += 1
    return out.decode()


def _is_dir(path):
    try:
        return os.stat(path)[0] & 0x4000 != 0
    except OSError:
        return False


def _walk(path, out):
    for name, kind, *_ in os.ilistdir(path):
        full = path + name
        if kind == 0x4000:
            _walk(full + "/", out)
            out.append((full, ""))
        else:
            h = hashlib.sha256()
            buf = bytearray(CHUNK)
            with open(full, "rb") as f:
                while True:
                    n = f.readinto(buf)
                    if not n:
                        break
                    h.update(buf if n == CHUNK else buf[:n])
            out.append((full, binascii.hexlify(h.digest()).decode()))


def _rmtree(path):
    if _is_dir(path):
        for name, *_ in os.ilistdir(path):
            _rmtree(path + "/" + name)
        os.rmdir(path)
    else:
        os.remove(path)


def _makedirs(path):
    parts = path.strip("/").split("/")
    cur = ""
    for p in parts:
        cur += "/" + p
        if not _is_dir(cur):
            os.mkdir(cur)


async def _reply(writer, status, body=b"", ctype="text/plain"):
    if isinstance(body, str):
        body = body.encode()
    writer.write(("HTTP/1.0 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
                  "Connection: close\r\n\r\n" % (status, ctype, len(body))).encode())
    if body:
        writer.write(body)
    await writer.drain()


class Ota:
    def __init__(self):
        self.token = None
        self.server = None
        self.pending_reset = False

    async def _handle(self, reader, writer):
        try:
            line = (await reader.readline()).decode().strip()
            method, target, _ = (line.split(" ") + ["", "", ""])[:3]
            headers = {}
            while True:
                h = (await reader.readline()).decode().strip()
                if not h:
                    break
                k, _, v = h.partition(":")
                headers[k.strip().lower()] = v.strip()
            if headers.get("x-token") != self.token:
                await _reply(writer, "403 Forbidden", "bad token\n")
                return
            route, _, query = target.partition("?")
            path = ""
            for kv in query.split("&"):
                if kv.startswith("p="):
                    path = _unquote(kv[2:])
            if path and (not path.startswith("/") or ".." in path):
                await _reply(writer, "400 Bad Request", "bad path\n")
                return

            if method == "GET" and route == "/files":
                entries = []
                _walk("/", entries)
                await _reply(writer, "200 OK", "".join("%s %s\n" % e for e in entries))
            elif method == "PUT" and route == "/file" and path:
                left = int(headers.get("content-length", "-1"))
                if left < 0:
                    await _reply(writer, "411 Length Required")
                    return
                parent = path.rsplit("/", 1)[0]
                if parent:
                    _makedirs(parent)
                tmp = path + ".tmp"
                with open(tmp, "wb") as f:
                    while left > 0:
                        chunk = await reader.read(min(CHUNK, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                if left:
                    os.remove(tmp)
                    await _reply(writer, "400 Bad Request", "short body\n")
                    return
                try:
                    os.remove(path)
                except OSError:
                    pass
                os.rename(tmp, path)
                print("ota: wrote", path)
                await _reply(writer, "200 OK", "ok\n")
            elif method == "PUT" and route == "/dir" and path:
                _makedirs(path)
                await _reply(writer, "200 OK", "ok\n")
            elif method == "DELETE" and route == "/file" and path:
                _rmtree(path)
                print("ota: removed", path)
                await _reply(writer, "200 OK", "ok\n")
            elif method == "POST" and route == "/reset":
                await _reply(writer, "200 OK", "resetting\n")
                self.pending_reset = True
            else:
                await _reply(writer, "404 Not Found", "no such endpoint\n")
        except Exception as ex:  # one bad request must not kill the server
            print("ota: request failed:", repr(ex))
            try:
                await _reply(writer, "500 Internal Server Error", repr(ex) + "\n")
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            if self.pending_reset:
                await aio.sleep_ms(300)
                machine.reset()

    async def run(self):
        from lib import power as power_mod
        self.token = _token()
        if not self.token:
            print("ota: no", TOKEN_PATH, "- OTA off")
            return
        # wifi.connect() blocks everything while it scans/joins, so back off
        # (up to MAX_BACKOFF_S) while no known network works.
        backoff = RETRY_S
        while True:
            if power_mod.on_battery():
                if self.server:
                    self.server.close()
                    self.server = None
                    _log("on battery, server stopped")
                await aio.sleep(RETRY_S)
                continue
            try:
                ip = wifi.connect()
                backoff = RETRY_S
            except Exception as ex:
                print("ota: wifi:", repr(ex), "- retry in", backoff, "s")
                await aio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_S)
                continue
            if not self.server:
                self.server = await aio.start_server(self._handle, "0.0.0.0", PORT)
                _log("listening on http://%s.local:%d (%s)" % (wifi.HOSTNAME, PORT, ip))
            await aio.sleep(RETRY_S)


ota = Ota()
