"""XKCD app: a random comic every 5 minutes.

Needs WiFi credentials in /data/wifi.json (see lib/wifi.py).
User A: fetch a new comic now.

LEDs: blue while downloading, off when the comic is on its way to the panel,
red if something failed (it retries a minute later).
"""

import gc
import json
import os
import random
import time

import socket
import ssl

import lvgl

from apps.base_app import BaseApp
from lib import fit_png, wifi
from lib.button import UserA
from lib.epd import display, display_height, display_width
from lib.led_bar import leds

UPDATE_S = 5 * 60
RETRY_S = 60
MAX_DOWNLOAD = 1500000  # bytes; larger PNGs don't fit comfortably in RAM
MIN_SCALE = 0.6  # skip comics that would shrink below this (unreadable)
TRIES = 6  # random picks per update before giving up

HEADER_H = 44
FOOTER_MIN_H = 40  # only show alt text if at least this much room is left
MARGIN = 6
USER_AGENT = b"BillboardBadge-xkcd/1.0 (MicroPython)"

_WHITE = lvgl.color_hex(0xFFFFFF)
_BLACK = lvgl.color_hex(0x000000)
_RED = lvgl.color_hex(0xFF0000)


LOG_PATH = "/data/xkcd.log"


def log(*parts):
    """print() and also append to /data/xkcd.log, which survives a reset."""
    line = "%d " % time.ticks_ms() + " ".join(str(p) for p in parts)
    print("xkcd:", line)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


class SkipComic(Exception):
    """This comic can't be shown; pick another."""


def _https_get(url, max_bytes, redirects=3):
    """Minimal HTTPS GET returning the body as a bytearray.

    MicroPython's requests crashed the badge reading image bodies, so this
    talks to the socket directly: the size comes from Content-Length and the
    body is read into one buffer allocated up front.
    """
    if not url.startswith("https://"):
        raise SkipComic("not https: " + url)
    host, _, path = url[8:].partition("/")
    addr = socket.getaddrinfo(host, 443)[0][-1]
    sock = socket.socket()
    try:
        sock.settimeout(20)
        sock.connect(addr)
        sock = ssl.wrap_socket(sock, server_hostname=host)
        sock.write(
            b"GET /" + path.encode() + b" HTTP/1.0\r\nHost: " + host.encode()
            + b"\r\nUser-Agent: " + USER_AGENT + b"\r\nConnection: close\r\n\r\n"
        )
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = sock.read(512)
            if not chunk:
                raise OSError("connection closed in headers")
            head += chunk
            if len(head) > 16384:
                raise OSError("headers too long")
        split = head.index(b"\r\n\r\n")
        body_start, head = head[split + 4:], head[:split].decode()
        lines = head.split("\r\n")
        status = int(lines[0].split(" ")[1])
        fields = {}
        for line in lines[1:]:
            k, _, v = line.partition(":")
            fields[k.strip().lower()] = v.strip()
        if status in (301, 302, 303, 307, 308) and redirects and "location" in fields:
            sock.close()
            return _https_get(fields["location"], max_bytes, redirects - 1)
        if status != 200:
            raise SkipComic("HTTP %d for %s" % (status, url))

        length = int(fields.get("content-length", "-1"))
        if length > max_bytes:
            raise SkipComic("too big: %d bytes" % length)
        if length >= 0:
            body = bytearray(length)
            body[:len(body_start)] = body_start
            mv = memoryview(body)
            got = len(body_start)
            while got < length:
                n = sock.readinto(mv[got:])
                if not n:
                    raise OSError("connection closed after %d of %d bytes" % (got, length))
                got += n
            return body
        body = bytearray(body_start)  # no Content-Length: read to EOF
        while True:
            chunk = sock.read(4096)
            if not chunk:
                return body
            body.extend(chunk)
            if len(body) > max_bytes:
                raise SkipComic("too big: over %d bytes" % max_bytes)
    finally:
        sock.close()


def _get(url, max_bytes=65536):
    log("GET", url)
    t = time.ticks_ms()
    body = _https_get(url, max_bytes)
    log("got", len(body), "bytes in", time.ticks_diff(time.ticks_ms(), t), "ms")
    return body


NEXT_PATH = "/data/xkcd_next"


def _take_requested():
    """Comic number from /data/xkcd_next (used once, then deleted), or 0.

    To show a particular comic next:
        mpremote exec "open('/data/xkcd_next','w').write('1773')"
    """
    try:
        with open(NEXT_PATH) as f:
            num = int(f.read().strip())
        os.remove(NEXT_PATH)
        log("requested #%d" % num)
        return num
    except (OSError, ValueError):
        return 0


class XkcdApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        super().__init__("XKCD")
        self.sleep_ms = 100
        self.next_update = 0
        self.latest = 0
        self._scr = None
        self._header = None
        self._footer = None
        self._alt = None

    # ---- data -------------------------------------------------------------

    def _latest(self):
        if not self.latest:
            self.latest = json.loads(bytes(_get("https://xkcd.com/info.0.json")))["num"]
            log("latest is", self.latest)
        return self.latest

    def _fetch(self):
        """Pick random comics until one is a PNG that fits; return (info, png)."""
        latest = self._latest()
        wanted = _take_requested()
        for _ in range(TRIES):
            num = wanted or random.randint(1, latest)
            wanted = 0
            if num == 404:  # there is no comic 404
                continue
            try:
                info = json.loads(bytes(_get("https://xkcd.com/%d/info.0.json" % num)))
                url = info["img"]
                if not url.endswith(".png"):
                    raise SkipComic("not a PNG: " + url)
                png = _get(url, MAX_DOWNLOAD)
                w, h = fit_png.png_size(png)
                box_w, box_h = self._box(0)
                fw, _ = fit_png.fit_size(w, h, box_w, box_h)
                if fw < w * MIN_SCALE:
                    raise SkipComic("would shrink to %d%%" % (fw * 100 // w))
                return info, png
            except SkipComic as ex:
                log("skip #%d: %s" % (num, ex))
            gc.collect()
        raise SkipComic("no usable comic in %d tries" % TRIES)

    # ---- drawing ----------------------------------------------------------

    @staticmethod
    def _box(footer_h):
        top = HEADER_H + MARGIN
        return display_width - 2 * MARGIN, display_height - top - MARGIN - footer_h

    def _ensure_screen(self):
        if self._scr is not None:
            return
        scr = lvgl.obj()
        scr.remove_style_all()
        scr.set_size(display_width, display_height)
        scr.set_style_bg_opa(lvgl.OPA.TRANSP, 0)

        header = lvgl.obj(scr)
        header.remove_style_all()
        header.set_pos(0, 0)
        header.set_size(display_width, HEADER_H)
        header.set_style_bg_color(_WHITE, 0)
        header.set_style_bg_opa(lvgl.OPA.COVER, 0)
        title = lvgl.label(header)
        title.set_width(display_width - 2 * MARGIN)
        title.set_pos(MARGIN, 6)
        title.set_style_text_font(lvgl.font_montserrat_28, 0)
        title.set_style_text_color(_BLACK, 0)

        footer = lvgl.obj(scr)
        footer.remove_style_all()
        footer.set_style_bg_color(_WHITE, 0)
        footer.set_style_bg_opa(lvgl.OPA.COVER, 0)
        alt = lvgl.label(footer)
        alt.set_width(display_width - 2 * MARGIN)
        alt.set_pos(MARGIN, 4)
        alt.set_style_text_font(lvgl.font_montserrat_16, 0)
        alt.set_style_text_color(_BLACK, 0)

        self._scr, self._header, self._title = scr, header, title
        self._footer, self._alt = footer, alt

    def _render_text(self, title, alt=None, alt_top=0):
        """Draw the header (and alt text below alt_top) through LVGL.

        Only the header/footer areas are flushed, so the comic already in the
        framebuffer stays untouched.
        """
        self._ensure_screen()
        self._title.set_text(title)
        show_alt = bool(alt) and display_height - alt_top >= FOOTER_MIN_H
        if show_alt:
            room = display_height - alt_top
            self._footer.set_pos(0, alt_top)
            self._footer.set_size(display_width, room)
            self._alt.set_text(alt)
            self._footer.remove_flag(lvgl.obj.FLAG.HIDDEN)
            # Shrink the footer to the text: every flushed pixel costs time.
            self._scr.update_layout()
            self._footer.set_height(min(room, self._alt.get_height() + 8))
        else:
            self._footer.add_flag(lvgl.obj.FLAG.HIDDEN)
        lvgl.screen_load(self._scr)
        self._scr.update_layout()
        display.lv_display.inv_p = 0  # drop the full-screen invalidation
        self._header.invalidate()
        if show_alt:
            self._footer.invalidate()
        lvgl.refr_now(display.lv_display)

    def _message(self, title, text):
        """Full-screen text, used for errors before any comic is shown."""
        display.clear()
        self._render_text(title, text, HEADER_H + MARGIN)
        display.update()

    def _show(self, info, png):
        display.clear()
        top = HEADER_H + MARGIN
        box_w, box_h = self._box(0)
        t = time.ticks_ms()
        log("drawing #%d" % info["num"], fit_png.png_size(png))
        _, y, _, h = fit_png.draw_fit(
            png, display._framebuffer_black, display._framebuffer_red,
            MARGIN, top, box_w, box_h,
        )
        log("drew #%d in %d ms" % (info["num"], time.ticks_diff(time.ticks_ms(), t)))
        png = None
        gc.collect()
        title = "#%d: %s" % (info["num"], info.get("safe_title") or info.get("title", ""))
        t = time.ticks_ms()
        self._render_text(title, info.get("alt"), y + h + MARGIN)
        log("text in %d ms, starting panel refresh" % time.ticks_diff(time.ticks_ms(), t))
        display.update()

    # ---- app loop ---------------------------------------------------------

    def _update(self):
        if not display.is_done_updating():
            self.next_update = time.time() + 5  # panel busy; try again shortly
            return
        try:
            # Fresh log each time the app is opened, and keep it under 8 KB
            # so a badge left running all weekend doesn't fill its flash.
            if self.launched or os.stat(LOG_PATH)[6] > 8192:
                with open(LOG_PATH, "w"):
                    pass
        except OSError:
            pass
        leds.fill((0, 0, 2))
        leds.write()
        try:
            log("wifi", wifi.connect())
            info, png = self._fetch()
            leds.fill((0, 0, 0))
            leds.write()
            self._show(info, png)
            self.next_update = time.time() + UPDATE_S
        except wifi.WifiError as ex:
            log("wifi error:", ex)
            leds.fill((2, 0, 0))
            leds.write()
            if self.launched:
                self._message("XKCD: no WiFi", str(ex) + "\nAdd it to data/wifi.json and push.")
            self.next_update = time.time() + RETRY_S
        except Exception as ex:  # network hiccups, bad PNGs, ...
            log("update failed:", repr(ex))
            leds.fill((2, 0, 0))
            leds.write()
            if self.launched:
                self._message("XKCD: download failed", repr(ex) + "\nRetrying every minute.")
            self.next_update = time.time() + RETRY_S
        gc.collect()

    def run(self):
        if self.launched or time.time() >= self.next_update:
            self._update()
        elif UserA.pressed():
            self._update()
