"""Decode and encode DSKE skeleton hierarchy blobs."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


@dataclass
class BoneNode:
    index: int
    children: list[int] = field(default_factory=list)


def decode_hierarchy(data: bytes, bone_count: int) -> dict[int, list[int]]:
    """Best-effort decode of the DSKE hierarchy section."""
    offset = 0
    header_count = struct.unpack_from("<I", data, offset)[0]
    offset += 8  # count + reserved

    if header_count != bone_count:
        raise ValueError(
            f"Hierarchy bone count {header_count} != name count {bone_count}"
        )

    parent_map: dict[int, int | None] = {0: None}
    child_lists: dict[int, list[int]] = {0: []}

    def read_node(expected_parent: int) -> None:
        nonlocal offset
        child_count = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        offset += 2  # padding / flags
        children: list[int] = []
        for _ in range(child_count):
            offset += 2  # child flags
            child_index = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            children.append(child_index)
            parent_map[child_index] = expected_parent
            read_node(child_index)
        child_lists[expected_parent] = children

    read_node(0)
    return child_lists


def encode_hierarchy(bone_count: int, child_lists: dict[int, list[int]]) -> bytes:
    """Encode hierarchy using the observed ForgeLight tree walk format."""
    parts = bytearray()
    parts.extend(struct.pack("<I", bone_count))
    parts.extend(struct.pack("<I", 0))

    def write_node(bone_index: int) -> None:
        children = child_lists.get(bone_index, [])
        parts.extend(struct.pack("<HH", len(children), 0))
        for child in children:
            parts.extend(struct.pack("<HH", 0xFFFF, 0))
            parts.extend(struct.pack("<HH", 0x0002, 0xFFFF))
            parts.extend(struct.pack("<I", child))
            write_node(child)

    write_node(0)
    return bytes(parts)


def child_lists_from_parents(bone_count: int, parents: list[int | None]) -> dict[int, list[int]]:
    """Build adjacency lists from a parent-index table (None/ -1 for root parent)."""
    child_lists: dict[int, list[int]] = {i: [] for i in range(bone_count)}
    for index, parent in enumerate(parents):
        if parent is None or parent < 0:
            if index != 0:
                child_lists.setdefault(0, []).append(index)
            continue
        child_lists.setdefault(parent, []).append(index)
    if 0 not in child_lists:
        child_lists[0] = []
    return child_lists


def bind_matrix_from_trs(
    translation: tuple[float, float, float],
    rotation_xyzw: tuple[float, float, float, float] | None = None,
) -> list[float]:
    """Pack a 3x4 row-major bind matrix (rotation + translation in row 3)."""
    if rotation_xyzw is None:
        row0 = (1.0, 0.0, 0.0, 0.0)
        row1 = (0.0, 1.0, 0.0, 0.0)
        row2 = (0.0, 0.0, 1.0, translation[2])
        # Observed files store translation in the fourth component of rows.
        row0 = (1.0, 0.0, 0.0, translation[0])
        row1 = (0.0, 1.0, 0.0, translation[1])
        row2 = (0.0, 0.0, 1.0, translation[2])
        return [*row0, *row1, *row2, 0.0, 0.0, 0.0, 1.0]

    import math

    x, y, z, w = rotation_xyzw
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z

    m00 = 1 - 2 * (yy + zz)
    m01 = 2 * (xy - wz)
    m02 = 2 * (xz + wy)
    m10 = 2 * (xy + wz)
    m11 = 1 - 2 * (xx + zz)
    m12 = 2 * (yz - wx)
    m20 = 2 * (xz - wy)
    m21 = 2 * (yz + wx)
    m22 = 1 - 2 * (xx + yy)
    tx, ty, tz = translation
    return [
        m00,
        m01,
        m02,
        tx,
        m10,
        m11,
        m12,
        ty,
        m20,
        m21,
        m22,
        tz,
        0.0,
        0.0,
        0.0,
        1.0,
    ]
