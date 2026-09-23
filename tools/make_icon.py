"""Generate assets/icon.ico and assets/icon.png from simple vector shapes.

Standard library only. Each size is rasterised directly (with 4x4
supersampling) rather than scaled down from 256px, so small sizes stay crisp.

    python tools/make_icon.py
"""

import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
SS = 4  # supersamples per axis

TILE = (10, 95, 180)      # #0a5fb4, matches the GUI's link colour
GLYPH = (255, 255, 255)
GAP = 0.035               # blue gap separating the front person from the back two


# -- geometry (unit square, y grows downward) --------------------------------

def in_round_rect(x, y, x0, y0, x1, y1, r):
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def in_circle(x, y, cx, cy, r):
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def in_shoulders(x, y, cx, cy, r, grow=0.0):
    """Upper half-disc with a flat base at cy (a person's shoulders)."""
    return y <= cy + grow and in_circle(x, y, cx, cy, r + grow)


def in_person(x, y, head, body, grow=0.0):
    hx, hy, hr = head
    bx, by, br = body
    return in_circle(x, y, hx, hy, hr + grow) or in_shoulders(x, y, bx, by, br, grow)


FRONT = ((0.50, 0.37, 0.115), (0.50, 0.79, 0.225))
BACK = [
    ((0.275, 0.42, 0.085), (0.275, 0.735, 0.155)),
    ((0.725, 0.42, 0.085), (0.725, 0.735, 0.155)),
]


def sample(x, y):
    """Return (rgb, alpha) for one point."""
    if not in_round_rect(x, y, 0.03, 0.03, 0.97, 0.97, 0.21):
        return None
    if in_person(x, y, *FRONT):
        return GLYPH
    if in_person(x, y, *FRONT, grow=GAP):
        return TILE
    if any(in_person(x, y, *p) for p in BACK):
        return GLYPH
    return TILE


def render(size):
    rows = []
    n = SS * SS
    for py in range(size):
        row = bytearray([0])  # PNG filter type: none
        for px in range(size):
            r = g = b = a = 0
            for sy in range(SS):
                for sx in range(SS):
                    c = sample((px + (sx + 0.5) / SS) / size, (py + (sy + 0.5) / SS) / size)
                    if c:
                        r += c[0]; g += c[1]; b += c[2]; a += 1
            if a:
                row += bytes((r // a, g // a, b // a, 255 * a // n))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return png(size, b"".join(rows))


# -- file formats ------------------------------------------------------------

def png(size, raw):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def ico(images):
    """images: list of (size, png_bytes). PNG-in-ICO is supported since Vista."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    return header + entries + blobs


def main():
    os.makedirs(ASSETS, exist_ok=True)
    images = [(s, render(s)) for s in ICO_SIZES]
    with open(os.path.join(ASSETS, "icon.ico"), "wb") as f:
        f.write(ico(images))
    with open(os.path.join(ASSETS, "icon.png"), "wb") as f:
        f.write(dict(images)[256])
    print("Wrote assets/icon.ico and assets/icon.png")


if __name__ == "__main__":
    main()
