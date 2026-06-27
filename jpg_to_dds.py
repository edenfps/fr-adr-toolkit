#!/usr/bin/env python3
"""Convert JPG/PNG palette texture to a minimal DDS for chatdy override."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PIL import Image


def write_dds(path: Path, image: Image.Image) -> None:
    image = image.convert("RGBA")
    width, height = image.size
    pixels = image.tobytes("raw", "BGRA")

    header = bytearray(128)
    header[0:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x000A1007)  # caps | height | width
    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 20, len(pixels))
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 0x41)  # DDPF_ALPHAPIXELS | DDPF_RGB
    struct.pack_into("<I", header, 84, 32)
    struct.pack_into("<I", header, 88, 0x20)  # RGBA8888
    struct.pack_into("<I", header, 108, 0x1000)  # DDSCAPS_TEXTURE

    path.write_bytes(bytes(header) + pixels)


def main() -> None:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".dds")
    image = Image.open(src)
    max_size = 512
    if max(image.size) > max_size:
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    write_dds(dst, image)
    print(f"Wrote {dst} ({image.size[0]}x{image.size[1]})")


if __name__ == "__main__":
    main()
