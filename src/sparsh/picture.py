"""A spot marked on a screenshot, for the person to say yes to.

A tap by position (phone.py, ``tap_at``) is held every time, and what
the person is shown is the picture with the spot ringed: "tap here?"
is a question a person can answer by looking, where "x 512, y 300" is
not.

Sparsh has no dependencies, so this reads and writes PNG itself -- the
kinds phones send (8 bits a channel, grey or colour, with or without
alpha, not interlaced). Anything else gives None, and the hold is shown
with the plain picture and the spot in words.

THE PICTURE IS MADE SMALLER, NEVER BIGGER: to at most ``WIDTH`` pixels
across, by a whole step (every 2nd or 3rd pixel), which is plenty for a
person to see where the ring is, and keeps the card light.
"""

from __future__ import annotations

import struct
import zlib

#: The widest a marked picture is made (in pixels).
WIDTH = 720
_SIGNATURE = b"\x89PNG\r\n\x1a\n"
#: Channels per colour type: grey, RGB, grey+alpha, RGBA.
_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}
_RING = (230, 30, 30)
_EDGE = (255, 255, 255)


def size(png: bytes) -> tuple[int, int] | None:
    """(width, height) from the PNG's header, or None."""
    if not png.startswith(_SIGNATURE) or png[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", png[16:24])


def mark(png: bytes, x: int, y: int) -> bytes | None:
    """The picture with a ring round (x, y) -- each 0 to 1000 across and
    down the picture -- as a PNG; None if this PNG can't be read here."""
    try:
        width, height, channels, rows = _decode(png)
    except (ValueError, zlib.error, struct.error):
        return None
    step = max(1, -(-width // WIDTH))
    small_w, small_h = -(-width // step), -(-height // step)
    # RGB rows, every ``step``-th pixel of every ``step``-th row
    pixels = [bytearray(small_w * 3) for _ in range(small_h)]
    for sy in range(small_h):
        _rgb(rows[sy * step], channels, step, pixels[sy])
    cx, cy = x * (small_w - 1) // 1000, y * (small_h - 1) // 1000
    outer = max(10, small_w * 6 // 100)
    _ring(pixels, cx, cy, outer + 3, outer + 6, _EDGE)
    _ring(pixels, cx, cy, outer - 4, outer + 3, _RING)
    _ring(pixels, cx, cy, outer - 7, outer - 4, _EDGE)
    _ring(pixels, cx, cy, 0, 4, _RING)
    _ring(pixels, cx, cy, 4, 6, _EDGE)
    return _encode(small_w, small_h, pixels)


def changed(before: bytes, after: bytes) -> float | None:
    """The share of the screen that differs between two screenshots, 0 to
    1, from every 4th pixel of every 4th row; a different size is all of
    it. None if either can't be read here."""
    try:
        w1, h1, c1, rows1 = _decode(before)
        w2, h2, c2, rows2 = _decode(after)
    except (ValueError, zlib.error, struct.error):
        return None
    if (w1, h1) != (w2, h2):
        return 1.0
    seen = differ = 0
    for y in range(0, h1, 4):
        a, b = rows1[y], rows2[y]
        for x in range(0, w1, 4):
            i, j = x * c1, x * c2
            seen += 1
            if max(abs(a[i + k] - b[j + k]) for k in range(min(c1, c2, 3))) > 48:
                differ += 1
    return differ / seen if seen else 0.0


def _decode(png: bytes) -> tuple[int, int, int, list[bytes]]:
    if not png.startswith(_SIGNATURE):
        raise ValueError("not a PNG")
    at, data, header = 8, [], None
    while at < len(png):
        length, kind = struct.unpack(">I4s", png[at : at + 8])
        body = png[at + 8 : at + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            data.append(body)
        elif kind == b"IEND":
            break
        at += 12 + length
    if header is None:
        raise ValueError("no header")
    width, height, depth, colour, _, _, interlace = header
    if depth != 8 or colour not in _CHANNELS or interlace:
        raise ValueError("a kind of PNG not read here")
    channels = _CHANNELS[colour]
    raw = zlib.decompress(b"".join(data))
    stride = width * channels
    rows: list[bytes] = []
    previous = bytes(stride)
    for r in range(height):
        start = r * (stride + 1)
        row = _unfilter(raw[start], bytearray(raw[start + 1 : start + 1 + stride]),
                        previous, channels)  # fmt: skip
        rows.append(row)
        previous = row
    return width, height, channels, rows


def _unfilter(kind: int, row: bytearray, up: bytes, bpp: int) -> bytes:
    n = len(row)
    if kind == 0:
        return bytes(row)
    if kind == 1:
        for i in range(bpp, n):
            row[i] = (row[i] + row[i - bpp]) & 255
    elif kind == 2:
        return bytes((a + b) & 255 for a, b in zip(row, up, strict=True))
    elif kind == 3:
        for i in range(n):
            left = row[i - bpp] if i >= bpp else 0
            row[i] = (row[i] + ((left + up[i]) >> 1)) & 255
    elif kind == 4:
        for i in range(n):
            a = row[i - bpp] if i >= bpp else 0
            b = up[i]
            c = up[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
    else:
        raise ValueError(f"PNG filter {kind}")
    return bytes(row)


def _rgb(row: bytes, channels: int, step: int, out: bytearray) -> None:
    span = channels * step
    if channels >= 3:
        for c in range(3):
            out[c::3] = row[c::span][: len(out) // 3]
    else:
        grey = row[::span][: len(out) // 3]
        for c in range(3):
            out[c::3] = grey


def _ring(pixels: list[bytearray], cx: int, cy: int, inner: int, outer: int,
          colour: tuple[int, int, int]) -> None:  # fmt: skip
    height, width = len(pixels), len(pixels[0]) // 3
    for y in range(max(0, cy - outer), min(height, cy + outer + 1)):
        dy2 = (y - cy) ** 2
        row = pixels[y]
        for x in range(max(0, cx - outer), min(width, cx + outer + 1)):
            d2 = (x - cx) ** 2 + dy2
            if inner * inner <= d2 <= outer * outer:
                row[x * 3 : x * 3 + 3] = bytes(colour)


def _encode(width: int, height: int, pixels: list[bytearray]) -> bytes:
    raw = b"".join(b"\0" + bytes(row) for row in pixels)

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (_SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))  # fmt: skip
