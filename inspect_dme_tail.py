"""Inspect DME trailing section after mesh buffers."""
import struct
from pathlib import Path


def read_dma_size(data: bytes) -> int:
    return struct.unpack_from("<I", data, 8)[0]


def mesh_end_offset(data: bytes) -> int:
    dma_size = read_dma_size(data)
    off = 12 + dma_size + 24 + 4  # bounds + mesh_count
    mesh_count = struct.unpack_from("<I", data, off - 4)[0]
    for _ in range(mesh_count):
        off += 16  # mat + unknown
        vsize, vcount = struct.unpack_from("<2i", data, off)
        off += 8
        isize, icount = struct.unpack_from("<2i", data, off)
        off += 8
        off += vsize * vcount + isize * icount
    return off


data = Path(r"c:\Users\bobya\FRController\chatdy\chatdy_lod0.dme").read_bytes()
off = mesh_end_offset(data)
tail = data[off:]
print(f"tail length: {len(tail)}")
print(f"first 256 bytes:\n{tail[:256].hex()}")

# try parsing as nested chunks like ADR
pos = 0
idx = 0
while pos < len(tail) and idx < 20:
    if pos + 4 > len(tail):
        break
    val = struct.unpack_from("<I", tail, pos)[0]
    print(f"  [{idx}] @{pos}: u32={val} raw={tail[pos:pos+8].hex()}")
    pos += 4
    idx += 1
