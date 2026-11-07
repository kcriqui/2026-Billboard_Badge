"""Scale a PNG to fit a box on the e-paper framebuffers.

Unlike lib/large_png, this takes PNG bytes (e.g. straight from a download),
handles grayscale, gray+alpha, RGB, RGBA and palette images, and scales the
picture up or down to fit the box while keeping its aspect ratio.

Each source pixel is sorted into white, black or red:
  - transparent (alpha < 128)                  -> white
  - red > 127 and green, blue < 128            -> red
  - luminance below `threshold` (128 for strongly coloured pixels) -> black
  - anything else                              -> white
A threshold above the usual 128 keeps anti-aliased line art from thinning out.
Two scaling paths:
  - enlarging (most XKCD comics): each source pixel is sorted as above, then
    the black/white result is enlarged with bilinear interpolation and cut at
    `grow_cut` (150, i.e. a bit bold). Cutting first keeps thin lines; the
    smooth enlarge gives evenly stepped tilted lines and an even line weight
    (nearest neighbour made them lumpy at odd scales like 1.28x).
  - shrinking: every screen pixel averages the source pixels it covers and
    turns black if that average is below `shrink_threshold` (default 200,
    i.e. bold). Plain thresholding or dithering breaks thin strokes apart;
    averaging then cutting high keeps text solid.
"""

import array
import gc
import io

import deflate
import micropython
from micropython import const

SCREEN_WIDTH = const(960)
_WHITE = const(0)
_BLACK = const(1)
_RED = const(2)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


@micropython.viper
def _kind(r: int, g: int, b: int, threshold: int) -> int:
    if r > 127 and g < 128 and b < 128:
        return _RED
    # Strong colours (e.g. bright green on black) use the plain midpoint; the
    # raised threshold is only there for anti-aliased gray edges.
    hi = r
    lo = r
    if g > hi:
        hi = g
    if b > hi:
        hi = b
    if g < lo:
        lo = g
    if b < lo:
        lo = b
    if hi - lo > 64:
        threshold = 128
    if (r * 77 + g * 150 + b * 29) >> 8 < threshold:
        return _BLACK
    return _WHITE


@micropython.viper
def _unfilter(filter_type: int, row, prev, bpp: int):
    if filter_type == 0:
        return
    if filter_type > 4:
        raise ValueError("bad png filter")
    d = ptr8(row)
    p = ptr8(prev)
    n = int(len(row))
    for i in range(n):
        a = 0
        c = 0
        e = 0
        if i >= bpp:
            a = d[i - bpp]
            c = p[i - bpp]
        b = p[i]
        if filter_type == 1:
            e = a
        elif filter_type == 2:
            e = b
        elif filter_type == 3:
            e = (a + b) >> 1
        else:
            est = a + b - c
            pa = est - a
            if pa < 0:
                pa = 0 - pa
            pb = est - b
            if pb < 0:
                pb = 0 - pb
            pc = est - c
            if pc < 0:
                pc = 0 - pc
            if pa <= pb and pa <= pc:
                e = a
            elif pb <= pc:
                e = b
            else:
                e = c
        d[i] = (d[i] + e) & 255


@micropython.viper
def _classify_lut(row, lut, depth: int, width: int, out):
    """Grayscale or palette rows: look each sample up in a 2^depth table."""
    src = ptr8(row)
    kinds = ptr8(lut)
    dst = ptr8(out)
    mask = (1 << depth) - 1
    s = 0
    for x in range(width):
        if depth == 8:
            s = src[x]
        else:
            bit = x * depth
            s = (src[bit >> 3] >> (8 - depth - (bit & 7))) & mask
        dst[x] = kinds[s]


@micropython.viper
def _classify_direct(row, channels: int, width: int, threshold: int, out):
    """8-bit gray+alpha, RGB and RGBA rows."""
    src = ptr8(row)
    dst = ptr8(out)
    k = 0
    for x in range(width):
        i = x * channels
        if channels == 2:
            v = src[i]
            k = int(_kind(v, v, v, threshold))
            if src[i + 1] < 128:
                k = _WHITE
        else:
            k = int(_kind(src[i], src[i + 1], src[i + 2], threshold))
            if channels == 4 and src[i + 3] < 128:
                k = _WHITE
        dst[x] = k


# ---- shrink path: average the source pixels behind each screen pixel ----
# A "code" is a pixel's brightness 0..254, or 255 for red.
_RED_CODE = const(255)


@micropython.viper
def _code(r: int, g: int, b: int) -> int:
    if r > 127 and g < 128 and b < 128:
        return _RED_CODE
    lum = (r * 77 + g * 150 + b * 29) >> 8
    hi = r
    lo = r
    if g > hi:
        hi = g
    if b > hi:
        hi = b
    if g < lo:
        lo = g
    if b < lo:
        lo = b
    if hi - lo > 64:  # strong colour: decide black/white at the midpoint now
        if lum < 128:
            return 0
        return 254
    if lum > 254:
        return 254
    return lum


@micropython.viper
def _code_direct(row, channels: int, width: int, out):
    src = ptr8(row)
    dst = ptr8(out)
    c = 0
    for x in range(width):
        i = x * channels
        if channels == 2:
            c = src[i]
            if c > 254:
                c = 254
            if src[i + 1] < 128:
                c = 254
        else:
            c = int(_code(src[i], src[i + 1], src[i + 2]))
            if channels == 4 and src[i + 3] < 128:
                c = 254
        dst[x] = c


@micropython.viper
def _accumulate(codes, src_w: int, dst_w: int, sums, reds):
    """Add one source row into the per-column totals of the current screen row."""
    c = ptr8(codes)
    s = ptr32(sums)
    r = ptr32(reds)
    for x in range(src_w):
        dx = x * dst_w // src_w
        v = c[x]
        if v == _RED_CODE:
            r[dx] = r[dx] + 1
        else:
            s[dx] = s[dx] + v


@micropython.viper
def _emit(sums, reds, colcount, rows: int, dst_w: int, dst_x: int, dy: int,
          threshold: int, black, red):
    """Turn the averaged totals into one screen row, then clear them."""
    s = ptr32(sums)
    r = ptr32(reds)
    n = ptr8(colcount)
    bk = ptr8(black)
    rd = ptr8(red)
    base = dy * SCREEN_WIDTH + dst_x
    for dx in range(dst_w):
        cnt = n[dx] * rows
        reds_here = r[dx]
        if cnt > 0:
            i = base + dx
            byte = i >> 3
            bit = 128 >> (i & 7)
            if reds_here * 2 >= cnt:
                rd[byte] = rd[byte] | bit
                bk[byte] = bk[byte] & (255 ^ bit)
            elif (s[dx] + reds_here * 254) // cnt < threshold:
                bk[byte] = bk[byte] | bit
                rd[byte] = rd[byte] & (255 ^ bit)
        s[dx] = 0
        r[dx] = 0


def _read_full(stream, buf):
    """readinto() may return less than asked for; keep reading."""
    mv = memoryview(buf)
    got = 0
    while got < len(buf):
        n = stream.readinto(mv[got:])
        if not n:
            raise ValueError("png data ends early")
        got += n


def _read(data):
    """Return (width, height, color_type, bit_depth, palette, trns, idat)."""
    if bytes(data[:8]) != _PNG_SIGNATURE:
        raise ValueError("not a png")
    mv = memoryview(data)
    pos = 8
    width = height = depth = ctype = 0
    palette = trns = None
    idat = bytearray()
    while pos + 8 <= len(data):
        length = int.from_bytes(bytes(mv[pos:pos + 4]), "big")
        name = bytes(mv[pos + 4:pos + 8])
        chunk = mv[pos + 8:pos + 8 + length]
        pos += 12 + length
        if name == b"IHDR":
            width = int.from_bytes(bytes(chunk[0:4]), "big")
            height = int.from_bytes(bytes(chunk[4:8]), "big")
            depth = chunk[8]
            ctype = chunk[9]
            if chunk[12]:
                raise ValueError("interlaced png")
        elif name == b"PLTE":
            palette = bytes(chunk)
        elif name == b"tRNS":
            trns = bytes(chunk)
        elif name == b"IDAT":
            idat.extend(chunk)
        elif name == b"IEND":
            break
    if ctype not in _CHANNELS:
        raise ValueError("png color type %d" % ctype)
    if depth == 16 or (depth != 8 and ctype not in (0, 3)):
        raise ValueError("png bit depth %d" % depth)
    return width, height, ctype, depth, palette, trns, idat


def fit_size(src_w, src_h, box_w, box_h, max_scale=3):
    """Largest size with the image's aspect ratio that fits the box."""
    if src_w * box_h > src_h * box_w:
        w, h = box_w, src_h * box_w // src_w
    else:
        w, h = src_w * box_h // src_h, box_h
    if w > src_w * max_scale:
        w, h = src_w * max_scale, src_h * max_scale
    return max(w, 1), max(h, 1)


def png_size(data):
    """(width, height) from the PNG header without decoding."""
    return int.from_bytes(bytes(data[16:20]), "big"), int.from_bytes(bytes(data[20:24]), "big")


def draw_fit(data, black, red, box_x, box_y, box_w, box_h, threshold=170,
             max_scale=3, shrink_threshold=200, grow_cut=150):
    """Decode PNG bytes into the framebuffers, centred in the box.

    The box must already be white. Returns (x, y, w, h) of the drawn image.
    """
    src_w, src_h, ctype, depth, palette, trns, idat = _read(data)
    dst_w, dst_h = fit_size(src_w, src_h, box_w, box_h, max_scale)
    dst_x = box_x + (box_w - dst_w) // 2
    dst_y = box_y + (box_h - dst_h) // 2

    channels = _CHANNELS[ctype]
    bpp = max(1, channels * depth // 8)
    row_bytes = (src_w * channels * depth + 7) // 8

    if dst_w < src_w:
        _draw_shrunk(src_w, src_h, ctype, depth, palette, trns, idat,
                     dst_x, dst_y, dst_w, dst_h, shrink_threshold, black, red)
        return dst_x, dst_y, dst_w, dst_h

    lut = None
    if ctype in (0, 3):
        lut = bytearray(1 << depth)
        for s in range(1 << depth):
            if ctype == 0:
                v = s * 255 // ((1 << depth) - 1)
                lut[s] = _kind(v, v, v, threshold)
            elif palette and s * 3 + 2 < len(palette):
                lut[s] = _kind(palette[s * 3], palette[s * 3 + 1], palette[s * 3 + 2], threshold)
                if trns and s < len(trns) and trns[s] < 128:
                    lut[s] = _WHITE

    # Classify the whole comic first (enlarged comics are at most ~948x616
    # source pixels, so this is < 600 KB), then enlarge it in one pass.
    kinds = bytearray(src_w * src_h)
    kmv = memoryview(kinds)
    gc.collect()
    for y, row in enumerate(_rows(idat, src_w, src_h, channels, depth)):
        out = kmv[y * src_w:(y + 1) * src_w]
        if lut is not None:
            _classify_lut(row, lut, depth, src_w, out)
        else:
            _classify_direct(row, channels, src_w, threshold, out)
    x0t, x1t, fxt = _bilinear_table(src_w, dst_w)
    y0t, y1t, fyt = _bilinear_table(src_h, dst_h)
    # Black where the interpolated darkness beats the cut (gray < grow_cut).
    cut = (255 - grow_cut) * 65536 // 255
    for dy in range(dst_h):
        _bilinear_row(kinds, y0t[dy] * src_w, y1t[dy] * src_w, fyt[dy],
                      x0t, x1t, fxt, dst_w, (dst_y + dy) * SCREEN_WIDTH + dst_x,
                      cut, black, red)
    return dst_x, dst_y, dst_w, dst_h


def _bilinear_table(src_n, dst_n):
    """Per output pixel: the two source pixels to blend and the weight
    (0..255) of the second, using the pixel-centre convention (as Pillow)."""
    a = array.array("H", bytes(2 * dst_n))
    b = array.array("H", bytes(2 * dst_n))
    f = bytearray(dst_n)
    for d in range(dst_n):
        s = ((2 * d + 1) * src_n * 256) // (2 * dst_n) - 128
        if s < 0:
            s = 0
        i = s >> 8
        a[d] = i
        b[d] = i + 1 if i + 1 < src_n else i
        f[d] = s & 255
    return a, b, f


@micropython.viper
def _bilinear_row(kinds, row_a: int, row_b: int, fy: int, x0t, x1t, fxt,
                  dst_w: int, base: int, cut: int, black, red):
    """One enlarged screen row from two classified source rows."""
    k = ptr8(kinds)
    X0 = ptr16(x0t)
    X1 = ptr16(x1t)
    FX = ptr8(fxt)
    bk = ptr8(black)
    rd = ptr8(red)
    gy = 256 - fy
    for dx in range(dst_w):
        x0 = X0[dx]
        x1 = X1[dx]
        fx = FX[dx]
        gx = 256 - fx
        dark = 0
        reds = 0
        p = k[row_a + x0]
        w = gx * gy
        if p == _BLACK:
            dark += w
        elif p == _RED:
            reds += w
        p = k[row_a + x1]
        w = fx * gy
        if p == _BLACK:
            dark += w
        elif p == _RED:
            reds += w
        p = k[row_b + x0]
        w = gx * fy
        if p == _BLACK:
            dark += w
        elif p == _RED:
            reds += w
        p = k[row_b + x1]
        w = fx * fy
        if p == _BLACK:
            dark += w
        elif p == _RED:
            reds += w
        i = base + dx
        byte = i >> 3
        bit = 128 >> (i & 7)
        if dark > cut:
            bk[byte] = bk[byte] | bit
            rd[byte] = rd[byte] & (255 ^ bit)
        elif reds > 32768:
            rd[byte] = rd[byte] | bit


def _rows(idat, src_w, src_h, channels, depth):
    """Yield unfiltered raw rows (the same buffer pair is reused)."""
    bpp = max(1, channels * depth // 8)
    row_bytes = (src_w * channels * depth + 7) // 8
    prev = bytearray(row_bytes)
    row = bytearray(row_bytes)
    head = bytearray(1)
    stream = deflate.DeflateIO(io.BytesIO(idat), deflate.ZLIB)
    try:
        for _ in range(src_h):
            _read_full(stream, head)
            _read_full(stream, row)
            _unfilter(head[0], row, prev, bpp)
            yield row
            prev, row = row, prev
    finally:
        stream.close()


def _draw_shrunk(src_w, src_h, ctype, depth, palette, trns, idat,
                 dst_x, dst_y, dst_w, dst_h, threshold, black, red):
    channels = _CHANNELS[ctype]
    lut = None
    if ctype in (0, 3):
        lut = bytearray(1 << depth)
        for s in range(1 << depth):
            if ctype == 0:
                v = s * 255 // ((1 << depth) - 1)
                lut[s] = _code(v, v, v)
            elif palette and s * 3 + 2 < len(palette):
                lut[s] = _code(palette[s * 3], palette[s * 3 + 1], palette[s * 3 + 2])
                if trns and s < len(trns) and trns[s] < 128:
                    lut[s] = 254
            else:
                lut[s] = 254
    # How many source columns land in each screen column.
    colcount = bytearray(dst_w)
    for x in range(src_w):
        colcount[x * dst_w // src_w] += 1
    codes = bytearray(src_w)
    sums = bytearray(4 * dst_w)
    reds = bytearray(4 * dst_w)
    gc.collect()
    cur = 0  # screen row being accumulated, relative to dst_y
    rows = 0
    for y, row in enumerate(_rows(idat, src_w, src_h, channels, depth)):
        dy = y * dst_h // src_h
        if dy != cur and rows:
            _emit(sums, reds, colcount, rows, dst_w, dst_x, dst_y + cur, threshold, black, red)
            rows = 0
        cur = dy
        if lut is not None:
            _classify_lut(row, lut, depth, src_w, codes)
        else:
            _code_direct(row, channels, src_w, codes)
        _accumulate(codes, src_w, dst_w, sums, reds)
        rows += 1
    if rows:
        _emit(sums, reds, colcount, rows, dst_w, dst_x, dst_y + cur, threshold, black, red)


# ---- readability check on the drawn result ---------------------------------

@micropython.viper
def _run_stats(black, x0: int, y0: int, w: int, h: int, hist, gaps):
    """Scan rows of the black plane in the box. hist[n] counts black runs of
    n pixels (n capped at 31); gaps[0] counts white gaps of <= 3 px and
    gaps[1] gaps of <= 40 px, only between ink on the same row."""
    bk = ptr8(black)
    H = ptr32(hist)
    G = ptr32(gaps)
    for yy in range(y0, y0 + h):
        run = 0
        state = 0      # 0 white, 1 black
        seen_ink = 0
        base = yy * SCREEN_WIDTH
        for xx in range(x0, x0 + w):
            i = base + xx
            v = (bk[i >> 3] >> (7 - (i & 7))) & 1
            if v == state:
                run += 1
                continue
            if state == 1:
                if run > 31:
                    run = 31
                H[run] = H[run] + 1
                seen_ink = 1
            elif seen_ink:
                if run <= 3:
                    G[0] = G[0] + 1
                if run <= 40:
                    G[1] = G[1] + 1
            state = v
            run = 1


def readability(black, x, y, w, h):
    """(median black stroke width in px, % of letter-sized gaps that are
    <= 3 px) for the drawn box. Small strokes and tight gaps mean text too
    small to read on the panel (calibrated by eye on 13 comics, 2026-11-06:
    readable ones had median 3-4 px and <= 37 %; unreadable 2 px and >= 40 %)."""
    hist = bytearray(4 * 32)
    gaps = bytearray(8)
    _run_stats(black, x, y, w, h, hist, gaps)
    counts = [int.from_bytes(hist[4 * i:4 * i + 4], "little") for i in range(32)]
    total = sum(counts)
    median = 0
    if total:
        acc = 0
        for n in range(32):
            acc += counts[n]
            if acc * 2 >= total:
                median = n
                break
    thin = int.from_bytes(gaps[0:4], "little")
    short = int.from_bytes(gaps[4:8], "little")
    return median, (100 * thin // short) if short else 0
