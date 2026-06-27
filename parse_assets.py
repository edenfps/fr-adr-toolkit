#!/usr/bin/env python3
"""ForgeLight / Free Realms asset format parser (research tool)."""

import struct
import sys
from pathlib import Path


def read_compressed_length(data: bytes, off: int) -> tuple[int, int]:
    b0 = data[off]
    off += 1
    if b0 < 128:
        return b0, off
    if b0 != 0xFF:
        b1 = data[off]
        off += 1
        return ((b0 & 0x7F) << 8) | b1, off
    return struct.unpack_from("<I", data, off)[0], off + 4


def read_null_str(data: bytes, off: int) -> tuple[str, int]:
    end = data.index(0, off)
    return data[off:end].decode("ascii", errors="replace"), end + 1


def parse_adr(path: Path) -> None:
    data = path.read_bytes()
    off = 0
    idx = 0
    print(f"=== ADR: {path.name} ({len(data)} bytes) ===")
    while off < len(data):
        def_type = data[off]
        off += 1
        size, off = read_compressed_length(data, off)
        chunk = data[off : off + size]
        off += size

        if def_type == 1:
            skel, _ = read_null_str(chunk, 0)
            print(f"  [{idx}] skeleton -> {skel!r}")
        elif def_type == 2:
            print(f"  [{idx}] model definition ({size} bytes):")
            c_off = 0
            while c_off < len(chunk):
                sub_type = chunk[c_off]
                c_off += 1
                sub_size, c_off = read_compressed_length(chunk, c_off)
                if sub_type == 1:
                    mesh, _ = read_null_str(chunk, c_off)
                    print(f"      mesh: {mesh!r}")
                elif sub_type == 2:
                    mat, _ = read_null_str(chunk, c_off)
                    print(f"      material: {mat!r}")
                else:
                    print(f"      sub_type={sub_type} size={sub_size} data={chunk[c_off:c_off+16].hex()}")
                c_off += sub_size
        elif def_type == 4:
            print(f"  [{idx}] actor params ({size} bytes): {chunk.hex()}")
        elif def_type == 7:
            slot, s_off = read_null_str(chunk, 0)
            anim_type = chunk[s_off]
            s_off += 1
            fname_size, s_off = read_compressed_length(chunk, s_off)
            fname, _ = read_null_str(chunk, s_off)
            tail = chunk[s_off + fname_size :]
            print(
                f"  [{idx}] anim slot={slot!r} type={anim_type} file={fname!r} "
                f"tail={tail[:12].hex()}"
            )
        else:
            print(f"  [{idx}] type={def_type} size={size}: {chunk[:32].hex()}")
        idx += 1
    print()


def parse_dsk(path: Path) -> None:
    data = path.read_bytes()
    assert data[:4] == b"DSKE"
    version = struct.unpack_from("<I", data, 4)[0]
    names_size = struct.unpack_from("<I", data, 8)[0]
    off = 12
    names_end = 12 + names_size
    bones = []
    while off < names_end:
        name, off = read_null_str(data, off)
        bones.append(name)

    print(f"=== DSK: {path.name} v{version}, {len(bones)} bones ===")
    for i, name in enumerate(bones):
        print(f"  {i:3d}: {name}")

    # hierarchy records: uint16 child_count, then child_count x (uint16 flags?, uint16 bone_index)
    print(f"\n  Hierarchy at offset {off}:")
    root_idx = 0
    rec_off = off
    # skip root marker (92 = 0x5c seen at start)
    first = struct.unpack_from("<I", data, rec_off)[0]
    print(f"    header dword: {first}")
    rec_off += 8  # 0x5c + padding?

    def dump_hier(bone_idx: int, depth: int = 0) -> int:
        nonlocal rec_off
        child_count = struct.unpack_from("<H", data, rec_off)[0]
        rec_off += 2
        pad = struct.unpack_from("<H", data, rec_off)[0]
        rec_off += 2
        indent = "    " + "  " * depth
        print(f"{indent}{bones[bone_idx]} ({bone_idx}) children={child_count} pad={pad:#x}")
        for _ in range(child_count):
            flags = struct.unpack_from("<H", data, rec_off)[0]
            rec_off += 2
            child = struct.unpack_from("<H", data, rec_off)[0]
            rec_off += 2
            dump_hier(child, depth + 1)
        return rec_off

    # Try parsing from offset 912 (after 0x5c header block)
    rec_off = 912
    child_count = struct.unpack_from("<H", data, rec_off)[0]
    print(f"  Root children at 912: {child_count}")
    rec_off += 4
    for _ in range(child_count):
        flags = struct.unpack_from("<H", data, rec_off)[0]
        rec_off += 2
        child = struct.unpack_from("<H", data, rec_off)[0]
        rec_off += 2
        print(f"    child bone {child} ({bones[child]}) flags={flags:#x}")

    # bind-pose matrices likely follow hierarchy
    remaining = len(data) - rec_off
    print(f"\n  Bytes after hierarchy scan: {remaining} (expect ~92 * 64 = 5888 for 4x4 float matrices)")
    print()


def parse_dme(path: Path) -> None:
    data = path.read_bytes()
    assert data[:4] == b"DMOD"
    version = struct.unpack_from("<I", data, 4)[0]
    dma_size = struct.unpack_from("<I", data, 8)[0]
    dma = data[12 : 12 + dma_size]
    off = 12 + dma_size
    bmin = struct.unpack_from("<3f", data, off)
    bmax = struct.unpack_from("<3f", data, off + 12)
    off += 24
    mesh_count = struct.unpack_from("<I", data, off)[0] if version >= 3 else struct.unpack_from("<I", dma, 28)[0]
    off += 4 if version >= 3 else 0

    print(f"=== DME: {path.name} v{version}, dma={dma_size}, meshes={mesh_count} ===")
    print(f"  bounds min={bmin} max={bmax}")

    for i in range(mesh_count):
        mat_idx, u2, u3, u4 = struct.unpack_from("<4i", data, off)
        off += 16
        vsize, vcount = struct.unpack_from("<2i", data, off)
        off += 8
        isize, icount = struct.unpack_from("<2i", data, off)
        off += 8
        vbytes = vcount * vsize
        ibytes = icount * isize
        print(
            f"  mesh[{i}] mat={mat_idx} vsize={vsize} verts={vcount} "
            f"isize={isize} indices={icount} u=({u2},{u3},{u4})"
        )
        off += vbytes + ibytes

    tail = len(data) - off
    print(f"  trailing data: {tail} bytes")
    if tail > 0:
        print(f"  tail header: {data[off:off+64].hex()}")
    print()


def parse_gr2(path: Path) -> None:
    data = path.read_bytes()
    magic = data[:8]
    print(f"=== GR2: {path.name} ({len(data)} bytes) ===")
    print(f"  magic: {magic.hex()}")
    # Granny file format: after header, section directory
    if len(data) >= 0x20:
        val = struct.unpack_from("<I", data, 0x18)[0]
        print(f"  dword@0x18: {val} (often section count)")
    # scan for bone name strings
    strings = []
    cur = b""
    for b in data:
        if 32 <= b < 127:
            cur += bytes([b])
        else:
            if len(cur) >= 4:
                strings.append(cur.decode())
            cur = b""
    bone_like = [s for s in strings if s.isupper() or "_" in s][:30]
    print(f"  string samples: {bone_like[:20]}")
    print()


def main() -> None:
    base = Path(sys.argv[1] if len(sys.argv) > 1 else "chatdy")
    parse_adr(base / "chatdy.adr")
    parse_dsk(base / "treeble.dsk")
    parse_dme(base / "chatdy_lod0.dme")
    for gr2 in sorted(base.glob("*.gr2")):
        parse_gr2(gr2)


if __name__ == "__main__":
    main()
