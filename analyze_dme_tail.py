"""Analyze DME trailing section structure."""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from fr_formats import DmeFile


def mesh_end(data: bytes) -> int:
    dma_size = struct.unpack_from("<I", data, 8)[0]
    off = 12 + dma_size + 24 + 4 + 16 + 16
    vsize, vcount = struct.unpack_from("<2i", data, off)
    off += 8
    isize, icount = struct.unpack_from("<2i", data, off)
    off += 8
    return off + vsize * vcount + isize * icount


def show(name: str) -> None:
    path = Path(
        r"c:\Users\bobya\Documents\Free Realms Unpacker\editz fr assets\FR Assets 2025-07-07"
    ) / name
    data = path.read_bytes()
    d = DmeFile.load(path)
    tail = data[mesh_end(data) :]
    m = d.meshes[0]
    print(f"\n=== {name} tail={len(tail)} verts={len(m.vertices)} idx={len(m.indices)} unk={m.unknown} ===")
    # interpret as u32 array
    count = len(tail) // 4
    vals = struct.unpack(f"<{count}I", tail)
    for i in range(min(40, count)):
        print(f"  [{i:2d}] {vals[i]:10d} ({vals[i]:#010x})")


if __name__ == "__main__":
    for file in ["ball_m_beach.dme", "penguin_01_lod0.dme", "chatdy_lod0.dme"]:
        show(file)
