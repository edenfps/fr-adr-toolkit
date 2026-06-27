"""Shared binary helpers for ForgeLight asset files."""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass
class Vec3:
    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


def read_compressed_length(data: bytes, offset: int) -> tuple[int, int]:
    first = data[offset]
    offset += 1
    if first < 0x80:
        return first, offset
    if first != 0xFF:
        second = data[offset]
        offset += 1
        return ((first & 0x7F) << 8) | second, offset
    value = struct.unpack_from("<I", data, offset)[0]
    return value, offset + 4


def read_null_terminated_string(data: bytes, offset: int) -> tuple[str, int]:
    end = data.index(0, offset)
    return data[offset:end].decode("ascii", errors="replace"), end + 1


def read_vec3(data: bytes, offset: int) -> tuple[Vec3, int]:
    x, y, z = struct.unpack_from("<3f", data, offset)
    return Vec3(x, y, z), offset + 12


def read_chunk_records(data: bytes) -> list[tuple[int, bytes]]:
    """Parse length-prefixed sub-records used inside ADR blocks."""
    records: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        record_type = data[offset]
        offset += 1
        size, offset = read_compressed_length(data, offset)
        payload = data[offset : offset + size]
        offset += size
        records.append((record_type, payload))
    return records
