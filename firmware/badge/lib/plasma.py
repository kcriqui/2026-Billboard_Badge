"""Full-screen dithered plasma in the panel's three colours.

A plasma field (sum of four sine waves from a 256-entry table) is turned into
dots with an 8x8 ordered (Bayer) dither: a pixel is inked when the field's
tone beats the matrix threshold at that position. Ordered dithering keeps the
texture stable between frames, so successive fast refreshes change gently.

Two layers, so red only needs the (slow) full refresh:
  layer(plane, ..., avoid=None)   - draws one plane from params
  - red: deep, slow field; redrawn on full refreshes only
  - black: surface field; redrawn each fast refresh, skipping red pixels
    (black + red on one pixel is an undriven waveform table)

params(...) builds the 12 ints a layer needs; the viper row function reads
them through ptr32. Runs on the laptop too (preview) with ptr8/ptr32 stubs.
"""

import array
import math

import micropython

W, H = 960, 672
ROW_BYTES = W // 8

SIN = bytearray(int(127.5 + 127.4 * math.sin(2 * math.pi * i / 256)) for i in range(256))

_B = (0, 32, 8, 40, 2, 34, 10, 42, 48, 16, 56, 24, 50, 18, 58, 26,
      12, 44, 4, 36, 14, 46, 6, 38, 60, 28, 52, 20, 62, 30, 54, 22,
      3, 35, 11, 43, 1, 33, 9, 41, 51, 19, 59, 27, 49, 17, 57, 25,
      15, 47, 7, 39, 13, 45, 5, 37, 63, 31, 55, 23, 61, 29, 53, 21)
BAYER = bytearray(v * 4 + 2 for v in _B)  # thresholds 2..254


@micropython.viper
def _row(plane, avoid, use_avoid: int, y: int, prm, sin_t, bayer):
    p = ptr8(plane)
    a = ptr8(avoid)
    P = ptr32(prm)
    s = ptr8(sin_t)
    b = ptr8(bayer)
    k1 = P[0]
    k2 = P[1]
    k3 = P[2]
    k4 = P[3]
    t1 = P[4]
    t2 = P[5]
    t3 = P[6]
    t4 = P[7]
    lo = P[8]
    span = P[9]
    ox = P[10]
    oy = P[11]
    base = y * 120
    brow = ((y + oy) & 7) * 8
    ty = s[((y * k2) >> 4) + t2 & 255]
    for xb in range(120):
        byte = 0
        mask = 128
        x = xb * 8
        while mask:
            f = (s[((x * k1) >> 4) + t1 & 255] + ty
                 + s[(((x + y) * k3) >> 4) + t3 & 255]
                 + s[(((x - y + 2048) * k4) >> 4) + t4 & 255])
            tone = lo + ((f * span) >> 10)
            if tone > b[brow + ((x + ox) & 7)]:
                if use_avoid == 0 or (a[base + xb] & mask) == 0:
                    byte |= mask
            mask >>= 1
            x += 1
        p[base + xb] = byte


def params(k1, k2, k3, k4, t1, t2, t3, t4, lo, span, ox=0, oy=0):
    """Frequencies k* in 1/16 table steps per pixel, phases t* (0..255), and
    tone = lo + field * span / 1020 (0..255; higher = more ink)."""
    return array.array("i", [int(v) for v in (k1, k2, k3, k4, t1, t2, t3, t4, lo, span, ox, oy)])


def layer(plane, prm, avoid=None):
    """Fill a whole 960x672 plane (bytearray of W*H/8) from params."""
    use = 1 if avoid is not None else 0
    av = avoid if avoid is not None else plane
    for y in range(H):
        _row(plane, av, use, y, prm, SIN, BAYER)


def from_weather(wx, step):
    """(red_params, black_params) for this space weather and update number.

    High contrast (Kevin, 2026-11-06): each layer's tone sweeps from below 0
    (clean white) to above 254 (solid colour) across the field, so the
    troughs are white and the peaks solid. Storms push both up."""
    speed = min(max(wx.get("speed") or 400, 250), 900)
    bt = min(max(wx.get("bt") or 5, 1), 40)
    bz = min(max(wx.get("bz") or 0, -40), 40)
    kp = min(max(wx.get("kp") or 1, 0), 9)
    storm = (wx.get("g") or 0) >= 1 or kp >= 5
    south = max(0, -bz)
    # red: deep, slow, broad; amount from Kp. Steep tone curve (span 2200)
    # so red is solid inside each blob with a dithered fading rim: solid red
    # survives fast black-only refreshes, isolated dithered red dots fade
    # (Kevin's option C, 2026-11-06). lo sets coverage: ~24 % at Kp 2.7.
    r_lo = -1330 + kp * 20 + (80 if storm else 0)
    red = params(5, 6, 3, 4, 40, 90, 160, 220, r_lo, 2200, 3, 5)
    # black: surface; waviness from southward Bz, density from Bt, drift from speed
    freq = 9 + int(south / 2) + int(kp)                   # 9..~40
    drift = int(4 + (speed - 250) / 30)                   # table steps per update
    b_span = 330 + bt * 3 + south * 3                     # density
    black = params(freq, freq + 3, freq // 2 + 2, freq // 2 + 5,
                   step * drift, 200 - step * drift // 2, step * drift * 2, 77 + step * drift,
                   -110, b_span)
    return red, black
