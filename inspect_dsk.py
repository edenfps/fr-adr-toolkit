"""Inspect DSK hierarchy section."""
import struct
from pathlib import Path

data = Path(r"c:\Users\bobya\FRController\chatdy\treeble.dsk").read_bytes()
names_size = struct.unpack_from("<I", data, 8)[0]
off = 12 + names_size
print("At hierarchy section:")
for i in range(0, 96, 4):
    val = struct.unpack_from("<I", data, off + i)[0]
    print(f"  +{i:2d}: {val:10d} ({data[off + i : off + i + 4].hex()})")

# Try: first u32=92, then array of parent indices?
bone_count = struct.unpack_from("<I", data, off)[0]
print(f"\nbone_count={bone_count}")
off += 8

# Maybe flat parent index list: 92 x int16 parent
parents = struct.unpack_from(f"<{bone_count}h", data, off)
print("first 20 parent indices:", parents[:20])
off2 = off + bone_count * 2
print(f"after parents at {off2}, next bytes: {data[off2:off2+32].hex()}")

# Or 92 x (child_count u16 + children...)
# remaining = 5156 bytes after names
remaining = len(data) - (12 + names_size)
print(f"remaining after names: {remaining}")

# matrices at end: 92 * 64 = 5888
matrix_start = len(data) - 92 * 64
print(f"matrix_start={matrix_start}, pre-matrix bytes: {matrix_start - (12+names_size)}")

m0 = struct.unpack_from("<16f", data, matrix_start)
print("last bone matrix row0:", m0[0:4])
