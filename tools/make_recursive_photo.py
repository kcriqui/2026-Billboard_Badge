#!/usr/bin/env python3
"""Paste the badge's own view into its screen in a photo, N levels deep (Droste).

    python3 tools/make_recursive_photo.py photo.jpg out.jpg [levels]
    python3 tools/make_photo.py out.jpg <name>

QUAD holds the badge screen corners measured on the 2026-11-06 webcam photo
(1280x720); measure them again for a new photo. Needs Pillow.
"""
import sys
from PIL import Image, ImageDraw, ImageOps
src = Image.open(sys.argv[1]).convert("RGB")
out = sys.argv[2]
levels = int(sys.argv[3]) if len(sys.argv) > 3 else 4
W, H = 960, 672
CENTRE = (0.5, 0.45)   # same crop as tools/make_photo.py
# Badge screen corners in the 1280x720 frame (TL, TR, BR, BL); bottom is just off-frame.
QUAD = [(514, 509), (814, 509), (826, 727), (515, 727)]

def solve(a, b):
    """Gaussian elimination for an 8x8 system."""
    n = len(b); m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c])); m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]

def perspective_coeffs(dst, srcpts):
    """PIL PERSPECTIVE data mapping output points dst -> input points srcpts."""
    a, b = [], []
    for (x, y), (u, v) in zip(dst, srcpts):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    return solve(a, b)

coeffs = perspective_coeffs(QUAD, [(0, 0), (W, 0), (W, H), (0, H)])
mask = Image.new("L", src.size, 0)
ImageDraw.Draw(mask).polygon(QUAD, fill=255)
g = src
for _ in range(levels):
    screen = ImageOps.fit(g, (W, H), Image.LANCZOS, centering=CENTRE)  # what the badge shows
    warped = screen.transform(src.size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    g = src.copy(); g.paste(warped, (0, 0), mask)
g.save(out, quality=95)
print("wrote", out)
