"""DSKE skeleton reader."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .common import read_null_terminated_string


@dataclass
class DskFile:
    version: int
    bone_names: list[str] = field(default_factory=list)
    raw_hierarchy: bytes = b""
    bind_pose_matrices: list[list[float]] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> DskFile:
        data = Path(path).read_bytes()
        if data[:4] != b"DSKE":
            raise ValueError("Expected DSKE magic")

        skeleton = cls(version=struct.unpack_from("<I", data, 4)[0])
        names_size = struct.unpack_from("<I", data, 8)[0]
        offset = 12
        names_end = offset + names_size

        while offset < names_end:
            name, offset = read_null_terminated_string(data, offset)
            skeleton.bone_names.append(name)

        skeleton.raw_hierarchy = data[names_end : len(data) - len(skeleton.bone_names) * 48]
        matrix_start = len(data) - len(skeleton.bone_names) * 48
        if matrix_start <= names_end:
            raise ValueError("Could not locate bind-pose matrix block")

        for index in range(len(skeleton.bone_names)):
            start = matrix_start + index * 48
            row0 = struct.unpack_from("<4f", data, start)
            row1 = struct.unpack_from("<4f", data, start + 16)
            row2 = struct.unpack_from("<4f", data, start + 32)
            skeleton.bind_pose_matrices.append([*row0, *row1, *row2, 0.0, 0.0, 0.0, 1.0])
        return skeleton
