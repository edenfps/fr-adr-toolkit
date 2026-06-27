"""ForgeLight DME version 4 reader (H1Z1 / PS2-style multi-stream meshes)."""

from __future__ import annotations

import struct
from pathlib import Path

from .common import Vec3, read_vec3
from .dma import DmaFile
from .dme import DmeFile, MeshChunk, SkinnedVertex


def load_dme_v4_bytes(data: bytes, name: str = "mesh") -> DmeFile:
    if data[:4] != b"DMOD":
        raise ValueError("Expected DMOD magic")

    version = struct.unpack_from("<I", data, 4)[0]
    if version != 4:
        raise ValueError(f"load_dme_v4_bytes expected version 4, got {version}")

    dma_size = struct.unpack_from("<I", data, 8)[0]
    dma = DmaFile.load_bytes(data[12 : 12 + dma_size])

    offset = 12 + dma_size
    bounds_min, offset = read_vec3(data, offset)
    bounds_max, offset = read_vec3(data, offset)
    mesh_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4

    mesh_file = DmeFile(
        version=version,
        dma=dma,
        bounds_min=bounds_min,
        bounds_max=bounds_max,
    )

    for mesh_index in range(mesh_count):
        header = struct.unpack_from("<8I", data, offset)
        offset += 32
        (
            _draw_call_offset,
            _draw_call_count,
            _bone_transform_count,
            _unknown,
            stream_count,
            index_size,
            index_count,
            vertex_count,
        ) = header

        streams: list[tuple[int, bytes]] = []
        for _ in range(stream_count):
            bytes_per_vertex = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            block_size = bytes_per_vertex * vertex_count
            streams.append((bytes_per_vertex, data[offset : offset + block_size]))
            offset += block_size

        index_bytes = data[offset : offset + index_size * index_count]
        offset += index_size * index_count

        vertices, indices = _decode_v4_mesh(
            streams,
            index_bytes,
            index_size,
            index_count,
            vertex_count,
            mesh_name=f"{name}[{mesh_index}]",
        )
        mesh_file.meshes.append(
            MeshChunk(
                material_index=0,
                unknown=(max(1, _draw_call_count), 24, -1),
                vertices=vertices,
                indices=indices,
            )
        )

    mesh_file.trailing_bytes = data[offset:]
    return mesh_file


def load_dme_v4(path: str | Path) -> DmeFile:
    file_path = Path(path)
    return load_dme_v4_bytes(file_path.read_bytes(), file_path.name)


def _decode_v4_mesh(
    streams: list[tuple[int, bytes]],
    index_bytes: bytes,
    index_size: int,
    index_count: int,
    vertex_count: int,
    mesh_name: str,
) -> tuple[list[SkinnedVertex], list[int]]:
    if not streams:
        raise ValueError(f"{mesh_name} has no vertex streams")
    if index_size not in (2, 4):
        raise ValueError(f"{mesh_name} unsupported index size {index_size}")

    indices: list[int] = []
    for index in range(index_count):
        if index_size == 2:
            indices.append(struct.unpack_from("<H", index_bytes, index * 2)[0])
        else:
            indices.append(struct.unpack_from("<I", index_bytes, index * 4)[0])

    stream0_bpv, stream0 = streams[0]
    if stream0_bpv < 12:
        raise ValueError(f"{mesh_name} stream0 stride too small: {stream0_bpv}")

    vertices: list[SkinnedVertex] = []
    stream1 = streams[1][1] if len(streams) > 1 else None
    stream1_bpv = streams[1][0] if len(streams) > 1 else 0

    for vertex_index in range(vertex_count):
        base0 = vertex_index * stream0_bpv
        position, _ = read_vec3(stream0, base0)
        uv = _read_uv(stream1, stream1_bpv, vertex_index) if stream1 else (0.0, 0.0)
        vertices.append(
            SkinnedVertex(
                position=position,
                bone_weights=(1.0, 0.0, 0.0),
                bone_indices=(0, 0, 0, 0),
                normal=Vec3(0.0, 1.0, 0.0),
                color=(255, 255, 255, 255),
                uv=uv,
            )
        )

    _compute_normals(vertices, indices)
    return vertices, indices


def _read_uv(stream_data: bytes, bytes_per_vertex: int, vertex_index: int) -> tuple[float, float]:
    base = vertex_index * bytes_per_vertex
    if bytes_per_vertex >= 12:
        u, v = struct.unpack_from("<ee", stream_data, base + 8)
        return float(u), float(v)
    if bytes_per_vertex >= 8:
        u, v = struct.unpack_from("<2f", stream_data, base)
        return u, v
    return 0.0, 0.0


def _compute_normals(vertices: list[SkinnedVertex], indices: list[int]) -> None:
    accum: list[list[float]] = [[0.0, 0.0, 0.0] for _ in vertices]

    for triangle_start in range(0, len(indices) - 2, 3):
        i0, i1, i2 = indices[triangle_start : triangle_start + 3]
        if max(i0, i1, i2) >= len(vertices):
            continue
        p0 = vertices[i0].position
        p1 = vertices[i1].position
        p2 = vertices[i2].position
        ux, uy, uz = p1.x - p0.x, p1.y - p0.y, p1.z - p0.z
        vx, vy, vz = p2.x - p0.x, p2.y - p0.y, p2.z - p0.z
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        for index in (i0, i1, i2):
            accum[index][0] += nx
            accum[index][1] += ny
            accum[index][2] += nz

    for vertex_index, normal_sum in enumerate(accum):
        length = (normal_sum[0] ** 2 + normal_sum[1] ** 2 + normal_sum[2] ** 2) ** 0.5
        if length <= 1e-8:
            continue
        vertices[vertex_index].normal = Vec3(
            normal_sum[0] / length,
            normal_sum[1] / length,
            normal_sum[2] / length,
        )
