"""DMOD mesh reader with ClrNrmUVSkin vertex decoding."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .common import Vec3, read_vec3
from .dma import DmaFile


@dataclass
class SkinnedVertex:
    position: Vec3
    bone_weights: tuple[float, float, float]
    bone_indices: tuple[int, int, int, int]
    normal: Vec3
    color: tuple[int, int, int, int]
    uv: tuple[float, float]


@dataclass
class MeshChunk:
    material_index: int
    unknown: tuple[int, int, int]
    vertices: list[SkinnedVertex] = field(default_factory=list)
    indices: list[int] = field(default_factory=list)
    vertex_stride: int = 52


@dataclass
class DmeFile:
    version: int
    dma: DmaFile
    bounds_min: Vec3
    bounds_max: Vec3
    meshes: list[MeshChunk] = field(default_factory=list)
    trailing_bytes: bytes = b""

    @classmethod
    def load(cls, path: str | Path) -> DmeFile:
        return cls.load_bytes(Path(path).read_bytes(), Path(path).name)

    @classmethod
    def load_bytes(cls, data: bytes, name: str = "mesh") -> DmeFile:
        if data[:4] != b"DMOD":
            raise ValueError("Expected DMOD magic")

        version = struct.unpack_from("<I", data, 4)[0]
        if version == 4:
            from .dme_v4 import load_dme_v4_bytes

            return load_dme_v4_bytes(data, name)

        dma_size = struct.unpack_from("<I", data, 8)[0]
        dma = DmaFile.load_bytes(data[12 : 12 + dma_size])

        offset = 12 + dma_size
        bounds_min, offset = read_vec3(data, offset)
        bounds_max, offset = read_vec3(data, offset)

        mesh_count = struct.unpack_from("<I", data, offset)[0] if version >= 3 else len(dma.materials)
        if version >= 3:
            offset += 4

        mesh_file = cls(
            version=version,
            dma=dma,
            bounds_min=bounds_min,
            bounds_max=bounds_max,
        )

        for _ in range(mesh_count):
            material_index, unknown_a, unknown_b, unknown_c = struct.unpack_from(
                "<4i", data, offset
            )
            offset += 16
            vertex_size, vertex_count = struct.unpack_from("<2i", data, offset)
            offset += 8
            index_size, index_count = struct.unpack_from("<2i", data, offset)
            offset += 8

            vertex_bytes = data[offset : offset + vertex_size * vertex_count]
            offset += vertex_size * vertex_count
            index_bytes = data[offset : offset + index_size * index_count]
            offset += index_size * index_count

            chunk = MeshChunk(
                material_index=material_index,
                unknown=(unknown_a, unknown_b, unknown_c),
                vertex_stride=vertex_size,
            )
            if vertex_size == 52:
                chunk.vertices = decode_clr_nrm_uv_skin_vertices(vertex_bytes, vertex_count)
            elif vertex_size == 36:
                chunk.vertices = decode_clr_nrm_uv_vertices(vertex_bytes, vertex_count)
            else:
                raise ValueError(
                    f"Unsupported vertex stride {vertex_size} in {name}; "
                    "supported layouts: 36-byte ClrNrmUV, 52-byte ClrNrmUVSkin"
                )

            for index in range(index_count):
                if index_size == 2:
                    chunk.indices.append(
                        struct.unpack_from("<H", index_bytes, index * 2)[0]
                    )
                elif index_size == 4:
                    chunk.indices.append(
                        struct.unpack_from("<I", index_bytes, index * 4)[0]
                    )
                else:
                    raise ValueError(f"Unsupported index size {index_size}")
            mesh_file.meshes.append(chunk)

        mesh_file.trailing_bytes = data[offset:]
        return mesh_file


def decode_clr_nrm_uv_vertices(data: bytes, count: int) -> list[SkinnedVertex]:
    """Decode rigid Position/Normal/Color/Texcoord layout (36 bytes)."""
    vertices: list[SkinnedVertex] = []
    for index in range(count):
        base = index * 36
        position, _ = read_vec3(data, base)
        normal, _ = read_vec3(data, base + 12)
        color = struct.unpack_from("<4B", data, base + 24)
        uv = struct.unpack_from("<2f", data, base + 28)
        vertices.append(
            SkinnedVertex(
                position=position,
                bone_weights=(1.0, 0.0, 0.0),
                bone_indices=(0, 0, 0, 0),
                normal=normal,
                color=color,
                uv=uv,
            )
        )
    return vertices


def decode_clr_nrm_uv_skin_vertices(data: bytes, count: int) -> list[SkinnedVertex]:
    """Decode the Position/BlendWeight/BlendIndices/Normal/Color/Texcoord layout."""
    vertices: list[SkinnedVertex] = []
    for index in range(count):
        base = index * 52
        position, _ = read_vec3(data, base)
        weights = struct.unpack_from("<3f", data, base + 12)
        bone_indices = struct.unpack_from("<4B", data, base + 24)
        normal, _ = read_vec3(data, base + 28)
        color = struct.unpack_from("<4B", data, base + 40)
        uv = struct.unpack_from("<2f", data, base + 44)
        vertices.append(
            SkinnedVertex(
                position=position,
                bone_weights=weights,
                bone_indices=bone_indices,
                normal=normal,
                color=color,
                uv=uv,
            )
        )
    return vertices
