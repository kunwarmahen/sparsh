"""The spot ringed on a screenshot: read and written without a library.

The bias: A PICTURE THAT CAN'T BE MARKED IS NONE, NEVER A CRASH -- the
hold is then shown with the plain picture and the spot in words.
"""

import zlib

from sparsh import picture


def flat(width, height, colour=(0, 0, 0)):
    return picture._encode(width, height, [bytearray(colour * width) for _ in range(height)])


def pixel(png, x, y):
    width, _, channels, rows = picture._decode(png)
    return tuple(rows[y][x * channels : x * channels + 3])


def test_a_ring_round_the_spot_and_the_middle_left_alone():
    marked = picture.mark(flat(400, 800), 500, 500)
    assert picture.size(marked) == (400, 800)
    assert pixel(marked, 199, 399) == picture._RING  # the dot in the middle
    ring = max(10, 400 * 6 // 100)
    assert pixel(marked, 199 + ring, 399) == picture._RING
    assert pixel(marked, 199 + ring // 2, 399) == (0, 0, 0)  # inside the ring
    assert pixel(marked, 10, 10) == (0, 0, 0)


def test_a_big_picture_is_made_smaller_by_a_whole_step():
    assert picture.size(picture.mark(flat(1080, 2400), 0, 0)) == (540, 1200)


def test_every_filter_a_phone_may_use_reads_back_the_same():
    width, height = 5, 5
    rows = [bytes((x * 40 + y * 7 + c) % 256 for x in range(width) for c in range(4))
            for y in range(height)]  # fmt: skip
    raw, up = b"", bytes(width * 4)
    for kind, row in zip(range(5), rows, strict=True):
        raw += bytes([kind]) + _filtered(kind, row, up, 4)
        up = row
    header = (width).to_bytes(4, "big") + (height).to_bytes(4, "big") + bytes([8, 6, 0, 0, 0])
    png = picture._SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw))
    assert picture._decode(png + _chunk(b"IEND", b""))[3] == rows


def test_what_cant_be_read_here_is_none():
    assert picture.mark(b"\x89PNG\r\n\x1a\n" + b"\0" * 16, 1, 1) is None
    assert picture.mark(b"not a picture", 1, 1) is None


def _chunk(kind, body):
    crc = zlib.crc32(kind + body) & 0xFFFFFFFF
    return len(body).to_bytes(4, "big") + kind + body + crc.to_bytes(4, "big")


def _filtered(kind, row, up, bpp):
    out = bytearray(len(row))
    for i, value in enumerate(row):
        a = row[i - bpp] if i >= bpp else 0
        b = up[i]
        c = up[i - bpp] if i >= bpp else 0
        if kind == 4:
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            guess = a if pa <= pb and pa <= pc else b if pb <= pc else c
        else:
            guess = (0, a, b, (a + b) >> 1)[kind]
        out[i] = (value - guess) & 255
    return bytes(out)


def test_two_screenshots_compared_by_how_much_differs():
    black, white = flat(40, 40), flat(40, 40, (255, 255, 255))
    assert picture.changed(black, black) == 0.0
    assert picture.changed(black, white) == 1.0
    assert picture.changed(black, flat(40, 80)) == 1.0  # another size
    assert picture.changed(black, b"not a picture") is None
