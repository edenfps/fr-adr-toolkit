"""DMAT material definition reader."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .common import read_null_terminated_string


@dataclass
class MaterialEntry:
    hash_value: int
    raw_parameters: bytes


@dataclass
class DmaFile:
    textures: list[str] = field(default_factory=list)
    materials: list[MaterialEntry] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> DmaFile:
        return cls.load_bytes(Path(path).read_bytes())

    @classmethod
    def load_bytes(cls, data: bytes) -> DmaFile:
        if data[:4] != b"DMAT":
            raise ValueError("Expected DMAT magic")

        dma = cls()
        offset = 8
        version = struct.unpack_from("<I", data, 4)[0]
        if version != 1:
            raise ValueError(f"Unsupported DMAT version {version}")

        texture_bytes = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        texture_end = offset + texture_bytes
        while offset < texture_end:
            texture, offset = read_null_terminated_string(data, offset)
            dma.textures.append(texture)

        material_count = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        for _ in range(material_count):
            hash_value = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            parameter_size = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            raw_parameters = data[offset : offset + parameter_size]
            offset += parameter_size
            dma.materials.append(
                MaterialEntry(hash_value=hash_value, raw_parameters=raw_parameters)
            )
        return dma
