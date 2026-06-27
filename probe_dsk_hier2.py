"""Experimental DSKE hierarchy parser v2."""

import struct
from pathlib import Path

data = Path(r"c:\Users\bobya\FRController\chatdy\treeble.dsk").read_bytes()
names_size = struct.unpack_from("<I", data, 8)[0]
start = 12 + names_size
offset = start + 12  # skip header + marker


def walk(offset: int, depth: int = 0) -> int:
    if offset + 4 > len(data) - 92 * 48:
        return offset
    child_count = struct.unpack_from("<I", data, offset)[0]
    if child_count > 50:
        return offset
    offset += 4
    print("  " * depth + f"children={child_count} @{offset-4}")
    for _ in range(child_count):
        marker = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        bone = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        print("  " * depth + f"  bone[{bone}] marker={marker:#x}")
        if marker == 0x2FFFF or (marker & 0xFFFF) == 0x2:
            offset = walk(offset, depth + 1)
        elif (marker >> 16) == 0x3:
            sub_count = marker & 0xFFFF
            print("  " * depth + f"    inline subs={sub_count}")
    return offset


walk(offset)
