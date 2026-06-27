"""Binary write helpers for ForgeLight asset files."""

from __future__ import annotations

import struct


def write_compressed_length(size: int) -> bytes:
    if size < 0x80:
        return bytes([size])
    if size < 0x7FFF:
        return bytes([(size >> 8) | 0x80, size & 0xFF])
    return b"\xFF" + struct.pack("<I", size)


def write_null_string(value: str) -> bytes:
    return value.encode("ascii", errors="replace") + b"\x00"


def write_string_record(record_type: int, value: str) -> bytes:
    payload = write_null_string(value)
    return bytes([record_type]) + write_compressed_length(len(payload)) + payload


def write_float_record(record_type: int, value: float, big_endian: bool = True) -> bytes:
    payload = struct.pack(">f" if big_endian else "<f", value)
    return bytes([record_type]) + write_compressed_length(len(payload)) + payload


def write_section(section_type: int, payload: bytes) -> bytes:
    return bytes([section_type]) + write_compressed_length(len(payload)) + payload
