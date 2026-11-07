"""XKCD app: a random comic every 5 minutes.

Needs WiFi credentials in /data/wifi.json (see lib/wifi.py).
User A: fetch a new comic now.
User B: redraw the current comic with a full refresh (clears ghosting, and
lets you compare a fast-refreshed comic with the same one done properly).

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
from lib import bitfont, fit_png, font_alt, wifi
from lib.button import UserA, UserB
from lib.epd import display, display_height, display_width
from lib.led_bar import leds

UPDATE_S = 5 * 60
RETRY_S = 60
# Fast refresh (~5 s, black/white only) for comics without red; a normal
# refresh when the app opens, when red is involved, and after this many fast
# ones in a row (clears ghosting; Kevin: full refresh every 10th). Set USE_FAST_REFRESH = False to go back to
# normal refreshes only (or create /data/no_fast_refresh on the badge).
USE_FAST_REFRESH = True
FAST_IN_A_ROW = 9  # so every 10th update is a full one
MAX_DOWNLOAD = 1500000  # bytes; larger PNGs don't fit comfortably in RAM
MIN_SCALE = 0.6  # skip comics that would shrink below this (unreadable)
# Readability, measured on the drawn comic (fit_png.readability). Skip if the
# median stroke is this thin or more of the letter gaps are this tight.
# Calibrated by Kevin on 13 comics (2026-11-06); the log records both numbers
# for every comic, to retune. Comics requested via /data/xkcd_next are shown
# regardless.
MIN_STROKE_PX = 3
MAX_TIGHT_GAPS_PCT = 40
READ_TRIES = 3  # unreadable comics in a row before showing one anyway
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
        self._fast_in_a_row = 0
        self._prev_had_red = True  # unknown screen contents: assume red

    # ---- data -------------------------------------------------------------

    def _latest(self):
        if not self.latest:
            self.latest = json.loads(bytes(_get("https://xkcd.com/info.0.json")))["num"]
            log("latest is", self.latest)
        return self.latest

    def _fetch(self):
        """Pick random comics until one is a PNG that fits; return (info, png)."""
        latest = self._latest()
        wanted = requested = _take_requested()
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
                return info, png, bool(requested) and num == requested
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

        self._scr, self._header, self._title = scr, header, title

    def _render_text(self, title, alt=None, alt_top=0):
        """Draw the alt text (below alt_top) and the title.

        The alt text uses the 1-bit bitmap font (lib/font_alt.py, DejaVu Sans
        15 px rendered on the laptop), drawn straight into the framebuffer:
        crisp on the panel, unlike LVGL's anti-aliased fonts. The title still
        goes through LVGL; only the header area is flushed, so the comic and
        the alt text stay untouched.
        """
        if alt and display_height - alt_top >= FOOTER_MIN_H:
            w = display_width - 2 * MARGIN
            lines = []
            for para in alt.split("\n"):
                lines += bitfont.wrap(font_alt, para, w)
            room = display_height - MARGIN - (alt_top + 2)
            max_lines = max(1, (room + 2) // (font_alt.HEIGHT + 2))
            bitfont.draw_lines(font_alt, display._framebuffer_black, lines,
                               MARGIN, alt_top + 2, w, max_lines)
        self._ensure_screen()
        self._title.set_text(title)
        lvgl.screen_load(self._scr)
        self._scr.update_layout()
        display.lv_display.inv_p = 0  # drop the full-screen invalidation
        self._header.invalidate()
        lvgl.refr_now(display.lv_display)

    def _message(self, title, text):
        """Full-screen text, used for errors before any comic is shown."""
        self._fast_in_a_row = 0
        self._prev_had_red = False
        display.clear()
        self._render_text(title, text, HEADER_H + MARGIN)
        display.update()

    def _comic_box(self, png, alt):
        """Comic area that leaves room for the whole alt text below it.

        The box is exactly as tall as the fitted comic, so short comics sit
        right under the title and tall ones shrink to make room. If showing
        all the text would shrink the comic below MIN_SCALE, drop text lines
        (draw_lines then ends with "...") until it doesn't.
        """
        box_w, full_h = self._box(0)
        w, h = fit_png.png_size(png)
        lines = 0
        if alt:
            for para in alt.split("\n"):
                lines += len(bitfont.wrap(font_alt, para, box_w))
        line_h = font_alt.HEIGHT + 2
        while True:
            text_h = lines * line_h + 2 * MARGIN if lines else 0
            fw, fh = fit_png.fit_size(w, h, box_w, full_h - text_h)
            if lines == 0 or (fw >= w * MIN_SCALE and full_h - text_h >= 60):
                return box_w, fh
            lines -= 1

    def _show(self, info, png, check=True):
        """Draw and refresh. Returns False (nothing refreshed) if `check` and
        the drawn comic is too small/busy to read on the panel."""
        display.clear()
        top = HEADER_H + MARGIN
        box_w, box_h = self._comic_box(png, info.get("alt"))
        t = time.ticks_ms()
        log("drawing #%d" % info["num"], fit_png.png_size(png))
        _, y, _, h = fit_png.draw_fit(
            png, display._framebuffer_black, display._framebuffer_red,
            MARGIN, top, box_w, box_h,
        )
        stroke, tight = fit_png.readability(display._framebuffer_black, MARGIN, y, box_w, h)
        readable = stroke >= MIN_STROKE_PX and tight < MAX_TIGHT_GAPS_PCT
        log("drew #%d in %d ms; stroke %d px, tight gaps %d%%%s" % (
            info["num"], time.ticks_diff(time.ticks_ms(), t), stroke, tight,
            "" if readable else " -> unreadable"))
        if check and not readable:
            return False
        png = None
        gc.collect()
        title = "#%d: %s" % (info["num"], info.get("safe_title") or info.get("title", ""))
        t = time.ticks_ms()
        self._render_text(title, info.get("alt"), y + h + MARGIN)
        has_red = max(display._framebuffer_red) != 0
        fast = (USE_FAST_REFRESH and not self.launched and not has_red
                and not self._prev_had_red and self._fast_in_a_row < FAST_IN_A_ROW)
        self._fast_in_a_row = self._fast_in_a_row + 1 if fast else 0
        self._prev_had_red = has_red
        log("text in %d ms, starting %s refresh%s" % (
            time.ticks_diff(time.ticks_ms(), t), "fast" if fast else "full",
            " (comic has red)" if has_red else ""))
        display.update(fast=fast)
        return True

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
            shown = False
            for attempt in range(READ_TRIES):
                info, png, requested = self._fetch()
                last = attempt == READ_TRIES - 1
                try:
                    shown = self._show(info, png, check=not (requested or last))
                except (ValueError, MemoryError) as ex:
                    # A PNG variant fit_png can't decode: try another comic
                    # rather than putting an error on the screen.
                    log("skip #%d: can't decode: %r" % (info["num"], ex))
                    png = None
                    gc.collect()
                    continue
                if shown:
                    break
                log("skip #%d: too small/busy to read on the badge" % info["num"])
                png = None
                gc.collect()
            if not shown:
                raise SkipComic("no comic could be shown in %d tries" % READ_TRIES)
            leds.fill((0, 0, 0))
            leds.write()
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
        elif UserB.pressed() and display.is_done_updating():
            # The comic is still in the framebuffers: just refresh it fully.
            log("full redraw of the current comic (User B)")
            self._fast_in_a_row = 0
            display.update(fast=False)
