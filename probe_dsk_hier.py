"""Experimental DSKE hierarchy parser."""

import struct
from pathlib import Path


def parse_node(data: bytes, offset: int, depth: int = 0) -> tuple[int, list[int]]:
    child_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    children: list[int] = []
    indent = "  " * depth
    print(f"{indent}node @{offset-4}: {child_count} children")
    for _ in range(child_count):
        marker = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        bone = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        print(f"{indent}  bone {bone} marker={marker:#010x}")
        children.append(bone)
        if marker & 0xFFFF0000 == 0x00020000 or marker == 0x0002FFFF:
            offset, sub = parse_node(data, offset, depth + 1)
            children.extend(sub)
    return offset, children


data = Path(r"c:\Users\bobya\FRController\chatdy\treeble.dsk").read_bytes()
names_size = struct.unpack_from("<I", data, 8)[0]
start = 12 + names_size
print("header", struct.unpack_from("<II", data, start))
off = start + 8
marker = struct.unpack_from("<I", data, off)[0]
print("marker", hex(marker))
off += 4
parse_node(data, off, 0)
