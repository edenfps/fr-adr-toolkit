#!/usr/bin/env python3
"""Detailed ForgeLight ADR / DSK / DME analysis."""

import struct
from pathlib import Path


def read_compressed_length(data: bytes, off: int) -> tuple[int, int]:
    b0 = data[off]
    off += 1
    if b0 < 128:
        return b0, off
    if b0 != 0xFF:
        return ((b0 & 0x7F) << 8) | data[off], off + 1
    return struct.unpack_from("<I", data, off)[0], off + 4


def read_null_str(data: bytes, off: int) -> tuple[str, int]:
    end = data.index(0, off)
    return data[off:end].decode("ascii", errors="replace"), end + 1


def parse_record(data: bytes, off: int) -> tuple[dict, int]:
    fields: dict = {}
    while off < len(data):
        rt = data[off]
        off += 1
        rls, off = read_compressed_length(data, off)
        rdata = data[off : off + rls]
        off += rls
        if rt == 1:
            fields.setdefault("strings", []).append(read_null_str(rdata, 0)[0])
        elif rt == 2:
            fields.setdefault("files", []).append(read_null_str(rdata, 0)[0])
        elif rt == 4 and len(rdata) == 4:
            fields.setdefault("floats", []).append(struct.unpack("<f", rdata)[0])
        elif rt == 5 and len(rdata) == 4:
            fields.setdefault("ints", []).append(struct.unpack("<i", rdata)[0])
        else:
            fields.setdefault("other", []).append((rt, rdata.hex()))
    return fields, off


def parse_adr(path: Path) -> None:
    data = path.read_bytes()
    off = 0
    print(f"=== ADR {path.name} ===")
    while off < len(data):
        t = data[off]
        off += 1
        sz, off = read_compressed_length(data, off)
        chunk = data[off : off + sz]
        off += sz

        if t == 1:
            st = chunk[0]
            _, co = read_compressed_length(chunk, 1)
            name, _ = read_null_str(chunk, co)
            print(f"type 1 skeleton: {name!r}")
        elif t == 2:
            print("type 2 model:")
            co = 0
            while co < len(chunk):
                st = chunk[co]
                co += 1
                ss, co = read_compressed_length(chunk, co)
                sub = chunk[co : co + ss]
                co += ss
                if st in (1, 2):
                    print(f"  {'mesh' if st == 1 else 'material'}: {read_null_str(sub, 0)[0]!r}")
                elif st == 4:
                    print(f"  scale: {struct.unpack('<f', sub)[0]}")
                else:
                    print(f"  sub{st}: {sub.hex()}")
        elif t in (9, 10):
            print(f"type {t} animation bank:")
            co = 0
            idx = 0
            while co < len(chunk):
                if chunk[co] == 0xFE:
                    print(f"  block header: {chunk[co:co+4].hex()}")
                    co += 4
                    continue
                rl, co = read_compressed_length(chunk, co)
                rec = chunk[co : co + rl]
                co += rl
                fields, _ = parse_record(rec, 0)
                slot = fields.get("strings", [None])[0]
                file = fields.get("files", [None])[0]
                floats = fields.get("floats", [])
                print(
                    f"  [{idx}] slot={slot!r} file={file!r} "
                    f"floats={floats}"
                )
                idx += 1
        elif t == 19:
            print("type 19 sockets/attachments:")
            co = 0
            while co < len(chunk):
                if chunk[co] == 0xFE:
                    co += 4
                    continue
                rl, co = read_compressed_length(chunk, co)
                rec = chunk[co : co + rl]
                co += rl
                fields, _ = parse_record(rec, 0)
                print(f"  {fields}")
        else:
            print(f"type {t} ({sz} bytes): {chunk[:24].hex()}")


def parse_dsk(path: Path) -> None:
    data = path.read_bytes()
    names_size = struct.unpack_from("<I", data, 8)[0]
    off = 12
    names_end = 12 + names_size
    bones = []
    while off < names_end:
        bones.append(read_null_str(data, off)[0])
        off = read_null_str(data, off)[1]

    print(f"\n=== DSK {path.name}: {len(bones)} bones, {len(data)} bytes ===")

    # After names: uint32 bone_count, uint32 0, then hierarchy blob
    bone_count = struct.unpack_from("<I", data, off)[0]
    off += 8
    print(f"bone_count field: {bone_count}")

    # Each hierarchy node: uint16 numChildren, uint16 pad, then numChildren * (uint16 flags, uint16 childIndex)
    def walk(bone_idx: int, depth: int = 0) -> None:
        nonlocal off
        nchild = struct.unpack_from("<H", data, off)[0]
        off += 2
        pad = struct.unpack_from("<H", data, off)[0]
        off += 2
        if depth < 2:
            print(f"{'  '*depth}{bones[bone_idx]} -> {nchild} children (pad={pad:#x})")
        for _ in range(nchild):
            flags = struct.unpack_from("<H", data, off)[0]
            off += 2
            child = struct.unpack_from("<H", data, off)[0]
            off += 2
            if depth < 1:
                print(f"{'  '*(depth+1)}-> {bones[child]} flags={flags:#x}")
            walk(child, depth + 1)

    hier_start = off
    walk(0)

    matrix_bytes = len(data) - off
    matrix_count = matrix_bytes // 64
    print(f"hierarchy ends at {off}, matrices: {matrix_count} x 64 bytes ({matrix_bytes} total)")
    if matrix_count >= 1:
        m = struct.unpack_from("<16f", data, off)
        print(f"matrix[0] row0: {m[0:4]}")


def parse_dme_tail(path: Path) -> None:
    data = path.read_bytes()
    dma_size = struct.unpack_from("<I", data, 8)[0]
    off = 12 + dma_size + 24 + 4
    mat_idx, u2, u3, u4 = struct.unpack_from("<4i", data, off)
    off += 16
    vsize, vcount = struct.unpack_from("<2i", data, off)
    off += 8
    isize, icount = struct.unpack_from("<2i", data, off)
    off += 8
    off += vsize * vcount + isize * icount

    tail = data[off:]
    print(f"\n=== DME tail {len(tail)} bytes ===")
    print(f"mesh meta: mat={mat_idx} u2={u2} u3={u3} u4={u4}")
    print(f"vertex {vsize}b x {vcount}, index {isize}b x {icount}")
    print(f"tail hex: {tail[:128].hex()}")

    # decode vertex layout manually
    v0 = data[12 + dma_size + 24 + 4 + 16 + 16 :][:vsize]
    print("\nvertex[0] layout guess:")
    print(f"  pos: {struct.unpack_from('<3f', v0, 0)}")
    print(f"  nrm: {struct.unpack_from('<3f', v0, 12)}")
    print(f"  @24 u16x2: {struct.unpack_from('<HH', v0, 24)}")
    print(f"  uv:  {struct.unpack_from('<2f', v0, 28)}")
    print(f"  @36: {v0[36:52].hex()}")


def parse_gr2(path: Path) -> None:
    data = path.read_bytes()
    print(f"\n=== GR2 {path.name} ({len(data)} bytes) ===")
    print(f"magic: {data[:8].hex()}")
    # Granny 2+ files have version at 0xC
    if len(data) > 16:
        print(f"dwords @0x10: {struct.unpack_from('<4I', data, 0x10)}")


if __name__ == "__main__":
    base = Path(r"c:\Users\bobya\FRController\chatdy")
    parse_adr(base / "chatdy.adr")
    parse_dsk(base / "treeble.dsk")
    parse_dme_tail(base / "chatdy_lod0.dme")
    parse_gr2(base / "chatdy_loc_walk.gr2")
