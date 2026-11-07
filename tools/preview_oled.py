#!/usr/bin/env python3
"""Preview OLED (128x64) screen layouts on the laptop, as the cracked panel
shows them: dead rows (odd rows 1-21 and 59, 61, 63) are blacked out.

    python3 tools/preview_oled.py out.png

Fonts are rendered like tools/make_bitmap_font.py (no anti-aliasing), so
text matches what the badge would draw. Needs Pillow.
"""

import random
import sys

from PIL import Image, ImageDraw, ImageFont

W, H, SCALE = 128, 64, 5
DEAD = set(range(1, 22, 2)) | {59, 61, 63}
DJ = "/usr/share/fonts/truetype/dejavu/"


def font(name, size):
    f = ImageFont.truetype(DJ + name, size)
    return f


def text(d, xy, s, f, anchor="la"):
    d.fontmode = "1"
    d.text(xy, s, font=f, fill=1, anchor=anchor)


def fit_font(name, s, max_w, max_size):
    for size in range(max_size, 8, -1):
        f = font(name, size)
        if f.getlength(s) <= max_w:
            return f
    return font(name, 9)


def wifi_icon(d, x, y, bars, total=4):
    """Bars in logical (half-height) rows: each bar 3 px wide."""
    for i in range(total):
        h = 2 + i * 2
        if i < bars:
            d.rectangle((x + i * 4, y + 8 - h, x + i * 4 + 2, y + 8), fill=1)
        else:
            d.point((x + i * 4 + 1, y + 8), fill=1)


def battery_icon(d, x, y, pct):
    d.rectangle((x, y, x + 16, y + 8), outline=1)
    d.rectangle((x + 17, y + 3, x + 18, y + 5), fill=1)
    fill = round(14 * pct / 100)
    if fill:
        d.rectangle((x + 2, y + 2, x + 1 + fill, y + 6), fill=1)


def status_strip(name, rssi, pct, usb):
    """Top strip, drawn at half height (128x11) and doubled to rows 0-21,
    so every logical row lands on a live even row."""
    im = Image.new("1", (W, 11), 0)
    d = ImageDraw.Draw(im)
    bars = 0 if rssi is None else 4 if rssi > -55 else 3 if rssi > -65 else 2 if rssi > -75 else 1
    wifi_icon(d, 0, 1, bars)
    small = font("DejaVuSansCondensed.ttf", 9)
    text(d, (18, 0), name if rssi is not None else "no WiFi", small)
    label = "USB" if usb else "%d%%" % pct
    lw = small.getlength(label)
    battery_icon(d, W - 19, 1, 100 if usb else pct)
    text(d, (W - 22 - lw, 0), label, small)
    return im.resize((W, 22), Image.NEAREST)


def menu_a(app, idx, n, ssid, rssi, pct, usb):
    """A: status strip on top, big name in the healthy band, page dots."""
    im = Image.new("1", (W, H), 0)
    im.paste(status_strip(ssid, rssi, pct, usb), (0, 0))
    d = ImageDraw.Draw(im)
    f = fit_font("DejaVuSansCondensed-Bold.ttf", app, W - 4, 20)
    text(d, (W // 2, 40), app, f, "mm")
    gap = 8
    x0 = W // 2 - (n - 1) * gap // 2
    for i in range(n):
        x = x0 + i * gap
        if i == idx:
            d.rectangle((x - 2, 54, x + 2, 58), fill=1)
        else:
            d.rectangle((x - 1, 56, x, 57), fill=1)
    return im


def menu_b(app, idx, n, ssid, rssi, pct, usb):
    """B: everything in the healthy band: arrows + name, then a status line."""
    im = Image.new("1", (W, H), 0)
    d = ImageDraw.Draw(im)
    small = font("DejaVuSansCondensed.ttf", 10)
    text(d, (W // 2, 2), "MENU  %d / %d" % (idx + 1, n), small, "ma")  # top strip: doubled-safe? no
    f = fit_font("DejaVuSansCondensed-Bold.ttf", app, W - 20, 18)
    text(d, (W // 2, 34), app, f, "mm")
    text(d, (1, 34), "<", small, "lm")
    text(d, (W - 1, 34), ">", small, "rm")
    line = "%s %ddBm   %s" % (ssid, rssi, "USB" if usb else "%d%%" % pct)
    text(d, (W // 2, 50), line, small, "mm")
    return im


def life(gens=40, seed=7):
    random.seed(seed)
    gw, gh = 64, 32
    g = [[1 if random.random() < 0.3 else 0 for _ in range(gw)] for _ in range(gh)]
    for _ in range(gens):
        n = [[sum(g[(y + dy) % gh][(x + dx) % gw] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) - g[y][x]
              for x in range(gw)] for y in range(gh)]
        g = [[1 if (n[y][x] == 3 or (g[y][x] and n[y][x] == 2)) else 0 for x in range(gw)] for y in range(gh)]
    im = Image.new("1", (W, H), 0)
    d = ImageDraw.Draw(im)
    for y in range(gh):
        for x in range(gw):
            if g[y][x]:
                d.rectangle((x * 2, y * 2, x * 2 + 1, y * 2 + 1), fill=1)
    return im


def panel(im, label):
    """Scale up like the real panel (blue-white pixels, dead rows dark)."""
    out = Image.new("RGB", (W * SCALE + 20, H * SCALE + 44), (40, 40, 40))
    px = im.load()
    d = ImageDraw.Draw(out)
    for y in range(H):
        for x in range(W):
            on = px[x, y] and y not in DEAD
            c = (200, 230, 255) if on else (8, 8, 12)
            d.rectangle((10 + x * SCALE, 34 + y * SCALE, 10 + x * SCALE + SCALE - 2,
                         34 + y * SCALE + SCALE - 2), fill=c)
    d.text((10, 8), label, fill=(255, 255, 255), font=font("DejaVuSans.ttf", 16))
    return out


def main():
    data = dict(app="Space Weather", idx=3, n=5, ssid="ACCD", rssi=-77, pct=78, usb=False)
    shots = [
        panel(menu_a(**data), "A: status strip on top, big name, page dots"),
        panel(menu_b(**data), "B: all text in the good rows, status line under"),
        panel(menu_a(**dict(data, app="XKCD", idx=4, usb=True)), "A with a short name, on USB"),
        panel(life(), "Idle: Game of Life, 2x2 cells (64x32)"),
    ]
    w, h = shots[0].size
    sheet = Image.new("RGB", (w * 2, h * 2), (40, 40, 40))
    for i, s in enumerate(shots):
        sheet.paste(s, ((i % 2) * w, (i // 2) * h))
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "oled_preview.png")


if __name__ == "__main__":
    main()
