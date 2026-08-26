#!/usr/bin/env python3
"""Render the app icon to PNG at the sizes the PWA manifest and iOS need.

Pure stdlib on purpose: icon generation shouldn't drag an image library into the build.  The
mark is drawn analytically (rounded square, bottle silhouette, speech-bubble dot) and
supersampled 4x for anti-aliasing.
"""

import math
import struct
import zlib
from pathlib import Path

SIZES = (180, 192, 512)
SUPERSAMPLE = 4

BACKGROUND_TOP = (18, 32, 38)
BACKGROUND_BOTTOM = (11, 20, 24)
GLASS = (94, 214, 189)
GLASS_DEEP = (46, 148, 137)
CORK = (214, 168, 106)


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[float, float, float]:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))  # type: ignore[return-value]


def _rounded_square(x: float, y: float, size: float, radius: float) -> bool:
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def _bottle(x: float, y: float, size: float) -> str | None:
    """Which part of the bottle, if any, covers this point.  Coordinates are in icon units."""
    u, v = x / size, y / size
    # Neck.
    if 0.30 <= v < 0.42 and abs(u - 0.5) <= 0.055:
        return "glass"
    # Cork.
    if 0.235 <= v < 0.30 and abs(u - 0.5) <= 0.062:
        return "cork"
    # Shoulder: neck width widens into the body.
    if 0.42 <= v < 0.52:
        t = (v - 0.42) / 0.10
        half = 0.055 + (0.185 - 0.055) * (t * t * (3 - 2 * t))
        if abs(u - 0.5) <= half:
            return "glass"
    # Body with a rounded base.
    if 0.52 <= v <= 0.775:
        half = 0.185
        if v > 0.735:
            t = (v - 0.735) / 0.04
            half = 0.185 * math.sqrt(max(0.0, 1 - t * t))
        if abs(u - 0.5) <= half:
            return "glass"
    return None


def _message_dot(x: float, y: float, size: float) -> bool:
    """Three dots inside the bottle body — the 'message' in the bottle."""
    u, v = x / size, y / size
    for du in (-0.075, 0.0, 0.075):
        if (u - (0.5 + du)) ** 2 + (v - 0.635) ** 2 <= 0.030**2:
            return True
    return False


def _render(size: int) -> bytes:
    hi = size * SUPERSAMPLE
    radius = hi * 0.22
    rows: list[bytearray] = []
    for py in range(hi):
        row = bytearray()
        for px in range(hi):
            x, y = px + 0.5, py + 0.5
            if not _rounded_square(x, y, hi, radius):
                row += bytes((0, 0, 0, 0))
                continue
            base = _lerp(BACKGROUND_TOP, BACKGROUND_BOTTOM, y / hi)
            part = _bottle(x, y, hi)
            if part == "cork":
                base = CORK
            elif part == "glass":
                if _message_dot(x, y, hi):
                    base = _lerp(BACKGROUND_TOP, BACKGROUND_BOTTOM, y / hi)
                else:
                    base = _lerp(GLASS, GLASS_DEEP, min(1.0, max(0.0, (y / hi - 0.3) / 0.5)))
            row += bytes((int(base[0]), int(base[1]), int(base[2]), 255))
        rows.append(row)
    return _downsample(rows, hi, size)


def _downsample(rows: list[bytearray], hi: int, size: int) -> bytes:
    out = bytearray()
    factor = SUPERSAMPLE
    for y in range(size):
        out.append(0)  # PNG filter type: none
        for x in range(size):
            totals = [0, 0, 0, 0]
            for sy in range(factor):
                row = rows[y * factor + sy]
                for sx in range(factor):
                    offset = (x * factor + sx) * 4
                    for c in range(4):
                        totals[c] += row[offset + c]
            count = factor * factor
            out += bytes(t // count for t in totals)
    return bytes(out)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))


def _png(raw: bytes, size: int) -> bytes:
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")
    )


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "frontend" / "public" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        path = out_dir / f"icon-{size}.png"
        path.write_bytes(_png(_render(size), size))
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
