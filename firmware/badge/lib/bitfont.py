"""Draw text with a 1-bit bitmap font straight into the black framebuffer.

Fonts come from tools/make_bitmap_font.py (e.g. lib/font_alt.py). Pixels are
pre-rendered on the laptop, so text is crisp on the panel and drawing is a
fast copy (no LVGL, no anti-aliasing to threshold).

    from lib import bitfont, font_alt
    lines = bitfont.wrap(font_alt, text, 948)
    bitfont.draw_lines(font_alt, black_fb, lines, 6, 600, 948, max_lines=3)
"""

import micropython
from micropython import const

SCREEN_WIDTH = const(960)
SCREEN_HEIGHT = const(672)

# Common Unicode punctuation in xkcd alt text -> ASCII the fonts have.
_SUBST = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "--", "…": "...", " ": " ",
    "é": "e", "è": "e", "à": "a", "ö": "o", "ü": "u",
}


def _clean(text):
    out = []
    for ch in text:
        if 32 <= ord(ch) <= 126:
            out.append(ch)
        elif ch in _SUBST:
            out.append(_SUBST[ch])
        elif ch in "\n\t":
            out.append(" ")
        else:
            out.append("?")
    return "".join(out)


def width(font, text):
    adv = font.ADV16
    first = font.FIRST
    return (sum(adv[ord(c) - first] for c in text) + 8) >> 4


def wrap(font, text, max_w):
    """Word-wrap to lines no wider than max_w pixels (long words are split)."""
    lines, cur = [], ""
    for word in _clean(text).split(" "):
        if not word:
            continue
        trial = word if not cur else cur + " " + word
        if width(font, trial) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        while width(font, word) > max_w:  # a word wider than the line
            n = len(word)
            while n > 1 and width(font, word[:n]) > max_w:
                n -= 1
            lines.append(word[:n])
            word = word[n:]
        cur = word
    if cur:
        lines.append(cur)
    return lines


@micropython.viper
def _blit(black, data, off: int, w: int, h: int, x: int, y: int):
    """Set black pixels for one glyph bitmap at (x, y), clipped to the screen."""
    fb = ptr8(black)
    g = ptr8(data)
    rb = (w + 7) >> 3
    for r in range(h):
        yy = y + r
        if yy < 0 or yy >= SCREEN_HEIGHT:
            continue
        row = off + r * rb
        base = yy * SCREEN_WIDTH
        for c in range(w):
            if g[row + (c >> 3)] & (128 >> (c & 7)):
                xx = x + c
                if xx >= 0 and xx < SCREEN_WIDTH:
                    i = base + xx
                    fb[i >> 3] = fb[i >> 3] | (128 >> (i & 7))


def draw(font, black, x, y, text):
    """Draw one line with its top-left at (x, y); returns the end x.
    The pen position is kept in 1/16 px and rounded per letter."""
    first, last = font.FIRST, font.LAST
    offs, widths, adv, data, h = font.OFFSETS, font.WIDTHS, font.ADV16, font.DATA, font.HEIGHT
    pen = x << 4
    for ch in _clean(text):
        i = ord(ch)
        if i < first or i > last:
            i = ord("?")
        i -= first
        _blit(black, data, offs[i], widths[i], h, (pen + 8) >> 4, y)
        pen += adv[i]
    return (pen + 8) >> 4


def draw_lines(font, black, lines, x, y, max_w, max_lines=None, line_gap=2):
    """Draw wrapped lines; if they don't all fit, end the last one with '...'.
    Returns the y just below the last line drawn."""
    step = font.HEIGHT + line_gap
    if max_lines is not None and len(lines) > max_lines:
        lines = list(lines[:max_lines])
        if lines:
            last = lines[-1]
            while last and width(font, last + "...") > max_w:
                last = last[:-1]
            lines[-1] = last.rstrip() + "..."
    for line in lines:
        draw(font, black, x, y, line)
        y += step
    return y
