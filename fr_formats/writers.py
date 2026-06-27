"""Write ForgeLight binary asset files."""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .dme_trailing import build_trailing, default_mesh_unknown
from .dma import DmaFile
from .dme import MeshChunk, SkinnedVertex, Vec3
from .write_helpers import (
    write_compressed_length,
    write_float_record,
    write_null_string,
    write_section,
    write_string_record,
)


def serialize_dma(template: DmaFile, replace_slot0: str | None = None) -> bytes:
    if template.textures:
        textures_blob = bytearray()
        for index, existing_name in enumerate(template.textures):
            name = replace_slot0 if index == 0 and replace_slot0 is not None else existing_name
            textures_blob.extend(write_null_string(name))
    elif replace_slot0 is not None:
        textures_blob = write_null_string(replace_slot0)
    else:
        raise ValueError("serialize_dma requires textures in template or replace_slot0")

    parts = bytearray(b"DMAT")
    parts.extend(struct.pack("<I", 1))
    parts.extend(struct.pack("<I", len(textures_blob)))
    parts.extend(textures_blob)

    if template.materials:
        parts.extend(struct.pack("<I", len(template.materials)))
        for material in template.materials:
            parts.extend(struct.pack("<II", material.hash_value, len(material.raw_parameters)))
            parts.extend(material.raw_parameters)
    else:
        default_hash = 0x5832A0E4
        default_params = bytes(160)
        parts.extend(struct.pack("<I", 1))
        parts.extend(struct.pack("<II", default_hash, len(default_params)))
        parts.extend(default_params)

    return bytes(parts)


def write_dma(
    path: Path,
    texture_name: str,
    template: DmaFile | None = None,
) -> None:
    if template and template.textures:
        path.write_bytes(serialize_dma(template, replace_slot0=texture_name))
        return
    path.write_bytes(serialize_dma(DmaFile(textures=[texture_name])))


def write_dma_copy(path: Path, template: DmaFile) -> None:
    """Write a DMA file preserving all texture slots and material hashes."""
    path.write_bytes(serialize_dma(template))


def write_dma_hybrid(
    path: Path,
    texture_source: DmaFile,
    material_source: DmaFile,
    texture_names: list[str] | None = None,
) -> None:
    """Write a DMA using H1Z1/foreign texture slots with Free Realms-safe materials."""
    hybrid = DmaFile(
        textures=list(texture_names if texture_names is not None else texture_source.textures),
        materials=list(material_source.materials),
    )
    path.write_bytes(serialize_dma(hybrid))


def write_dsk(
    path: Path,
    bone_names: list[str],
    bind_matrices: list[list[float]] | None = None,
    hierarchy_template: Path | None = None,
) -> None:
    if bind_matrices is None:
        bind_matrices = [_identity_bind_matrix() for _ in bone_names]

    names_blob = bytearray()
    for name in bone_names:
        names_blob.extend(write_null_string(name))

    hierarchy_blob = _flat_hierarchy(len(bone_names))
    if hierarchy_template and hierarchy_template.exists():
        template_data = hierarchy_template.read_bytes()
        names_size = struct.unpack_from("<I", template_data, 8)[0]
        names_end = 12 + names_size
        matrix_bytes = len(bone_names) * 48
        template_hier = template_data[names_end : len(template_data) - matrix_bytes]
        template_bone_count = struct.unpack_from("<I", template_hier, 0)[0]
        if template_bone_count == len(bone_names):
            hierarchy_blob = template_hier

    matrix_blob = bytearray()
    for matrix in bind_matrices:
        matrix_blob.extend(_pack_bind_matrix(matrix))

    parts = bytearray(b"DSKE")
    parts.extend(struct.pack("<II", 2, len(names_blob)))
    parts.extend(names_blob)
    parts.extend(hierarchy_blob)
    parts.extend(matrix_blob)
    path.write_bytes(bytes(parts))


def write_dme(
    path: Path,
    vertices: list[SkinnedVertex],
    indices: list[int],
    dma_bytes: bytes,
    trailing_template: bytes | None = None,
    mesh_unknown: tuple[int, int, int] | None = None,
    template_vertex_count: int | None = None,
    template_index_count: int | None = None,
    auto_trailing: bool = True,
    meshes: list[MeshChunk] | None = None,
) -> None:
    mesh_chunks = meshes or [
        MeshChunk(
            material_index=0,
            unknown=mesh_unknown or default_mesh_unknown(1),
            vertices=vertices,
            indices=indices,
        )
    ]

    all_vertices = [vertex for chunk in mesh_chunks for vertex in chunk.vertices]
    bounds_min, bounds_max = _compute_bounds(all_vertices)

    if mesh_unknown is None:
        mesh_unknown = mesh_chunks[0].unknown

    batch_count = struct.unpack_from("<I", trailing_template, 0)[0] if trailing_template else 1
    if (
        trailing_template is not None
        and len(mesh_chunks) > 1
        and batch_count > 1
    ):
        from .dme_trailing import patch_named_batch_trailing

        trailing_bytes = patch_named_batch_trailing(
            trailing_template,
            [(len(chunk.vertices), len(chunk.indices)) for chunk in mesh_chunks],
        )
    elif trailing_template is not None and mesh_unknown[0] > 1:
        trailing_bytes = build_trailing(
            len(mesh_chunks[0].vertices),
            len(mesh_chunks[0].indices),
            mesh_unknown,
            template_trailing=trailing_template,
            template_vertex_count=template_vertex_count,
            template_index_count=template_index_count,
        )
    elif trailing_template is not None and not auto_trailing:
        trailing_bytes = trailing_template
    elif trailing_template is not None:
        from .dme_trailing import patch_named_batch_trailing

        if struct.unpack_from("<I", trailing_template, 0)[0] > 1:
            trailing_bytes = patch_named_batch_trailing(
                trailing_template,
                [(len(chunk.vertices), len(chunk.indices)) for chunk in mesh_chunks],
            )
        else:
            trailing_bytes = build_trailing(
                len(mesh_chunks[0].vertices),
                len(mesh_chunks[0].indices),
                mesh_chunks[0].unknown,
                template_trailing=trailing_template,
                template_vertex_count=template_vertex_count,
                template_index_count=template_index_count,
            )
    elif auto_trailing:
        trailing_bytes = build_trailing(
            len(mesh_chunks[0].vertices),
            len(mesh_chunks[0].indices),
            mesh_chunks[0].unknown,
            template_trailing=trailing_template,
            template_vertex_count=template_vertex_count,
            template_index_count=template_index_count,
        )
    else:
        trailing_bytes = b""

    parts = bytearray(b"DMOD")
    parts.extend(struct.pack("<II", 3, len(dma_bytes)))
    parts.extend(dma_bytes)
    parts.extend(struct.pack("<3f", *bounds_min.as_tuple()))
    parts.extend(struct.pack("<3f", *bounds_max.as_tuple()))
    parts.extend(struct.pack("<I", len(mesh_chunks)))

    for chunk in mesh_chunks:
        index_size = 2 if max(chunk.indices, default=0) < 65536 else 4
        index_bytes = bytearray()
        for index in chunk.indices:
            if index_size == 2:
                index_bytes.extend(struct.pack("<H", index))
            else:
                index_bytes.extend(struct.pack("<I", index))

        parts.extend(struct.pack("<4i", chunk.material_index, *chunk.unknown))
        parts.extend(struct.pack("<2i", chunk.vertex_stride, len(chunk.vertices)))
        parts.extend(struct.pack("<2i", index_size, len(chunk.indices)))
        parts.extend(_encode_vertices(chunk.vertices, chunk.vertex_stride))
        parts.extend(index_bytes)

    if trailing_bytes:
        parts.extend(trailing_bytes)
    path.write_bytes(bytes(parts))


def write_adr_minimal(
    path: Path,
    skeleton_file: str,
    mesh_file: str,
    material_file: str,
    animations: list[tuple[str, str, float]],
    model_scale: float = 1.0,
    extra_sections: list[tuple[int, bytes]] | None = None,
) -> None:
    parts = bytearray()
    parts.extend(write_section(1, write_string_record(1, skeleton_file)))
    model_block = (
        write_string_record(1, mesh_file)
        + write_string_record(2, material_file)
        + write_float_record(4, model_scale)
    )
    parts.extend(write_section(2, model_block))

    bank = bytearray(b"\xFE\x03\x01\x01")
    for slot_name, gr2_file, speed in animations:
        record = (
            write_string_record(1, slot_name)
            + write_string_record(2, gr2_file)
            + write_float_record(4, speed)
        )
        bank.extend(write_compressed_length(len(record)))
        bank.extend(record)
    parts.extend(write_section(9, bytes(bank)))

    if extra_sections:
        for section_type, payload in extra_sections:
            parts.extend(write_section(section_type, payload))

    path.write_bytes(bytes(parts))


def clone_animation_bank(
    template_bank: bytes,
    actor_prefix: str,
    source_prefix: str,
) -> bytes:
    text = template_bank.decode("latin1")
    pattern = re.compile(re.escape(source_prefix) + r"([^\x00]+\.gr2)")
    return pattern.sub(lambda m: actor_prefix + m.group(1), text).encode("latin1")


def write_adr_preserve_template(
    path: Path,
    template_bytes: bytes,
    skeleton_file: str,
    mesh_file: str,
    material_file: str,
    model_scale: float,
) -> None:
    """Rewrite sections 1/2 while keeping every other ADR section from the template.

    Player actors such as human_m rely on extra sections (e.g. type 3 FX hooks and
    type 5 skintone variants). Rebuilding only sections 9/10/19 breaks local player load.
    """
    parts = bytearray()
    parts.extend(write_section(1, write_string_record(1, skeleton_file)))
    model_block = (
        write_string_record(1, mesh_file)
        + write_string_record(2, material_file)
        + write_float_record(4, model_scale)
    )
    parts.extend(write_section(2, model_block))

    offset = 0
    while offset < len(template_bytes):
        section_type = template_bytes[offset]
        offset += 1
        size, offset = _read_compressed_length(template_bytes, offset)
        chunk = template_bytes[offset : offset + size]
        offset += size
        if section_type in (1, 2):
            continue
        parts.extend(write_section(section_type, chunk))

    path.write_bytes(bytes(parts))


def extract_adr_section(adr_data: bytes, section_type: int) -> bytes | None:
    offset = 0
    while offset < len(adr_data):
        current_type = adr_data[offset]
        offset += 1
        size, offset = _read_compressed_length(adr_data, offset)
        chunk = adr_data[offset : offset + size]
        offset += size
        if current_type == section_type:
            return chunk
    return None


def _read_compressed_length(data: bytes, offset: int) -> tuple[int, int]:
    first = data[offset]
    offset += 1
    if first < 0x80:
        return first, offset
    if first != 0xFF:
        return ((first & 0x7F) << 8) | data[offset], offset + 1
    return struct.unpack_from("<I", data, offset)[0], offset + 4


def _identity_bind_matrix() -> list[float]:
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _pack_bind_matrix(matrix: list[float]) -> bytes:
    return struct.pack("<4f4f4f", *matrix[0:4], *matrix[4:8], *matrix[8:12])


def _flat_hierarchy(bone_count: int) -> bytes:
    parts = bytearray()
    parts.extend(struct.pack("<II", bone_count, 0))
    parts.extend(struct.pack("<I", 0x0001FFFF))
    parts.extend(struct.pack("<I", max(bone_count - 1, 0)))
    for index in range(1, bone_count):
        parts.extend(struct.pack("<II", 0xFFFF0000, index))
    return bytes(parts)


def _compute_bounds(vertices: list[SkinnedVertex]) -> tuple[Vec3, Vec3]:
    if not vertices:
        return Vec3(0, 0, 0), Vec3(0, 0, 0)
    xs = [vertex.position.x for vertex in vertices]
    ys = [vertex.position.y for vertex in vertices]
    zs = [vertex.position.z for vertex in vertices]
    return (
        Vec3(min(xs), min(ys), min(zs)),
        Vec3(max(xs), max(ys), max(zs)),
    )


def _encode_vertices(vertices: list[SkinnedVertex], stride: int = 52) -> bytes:
    blob = bytearray()
    for vertex in vertices:
        blob.extend(struct.pack("<3f", *vertex.position.as_tuple()))
        if stride == 36:
            blob.extend(struct.pack("<3f", *vertex.normal.as_tuple()))
            blob.extend(struct.pack("<4B", *vertex.color))
            blob.extend(struct.pack("<2f", *vertex.uv))
            continue
        if stride != 52:
            raise ValueError(f"Unsupported vertex stride {stride} for encoding")
        blob.extend(struct.pack("<3f", *vertex.bone_weights))
        blob.extend(struct.pack("<4B", *vertex.bone_indices))
        blob.extend(struct.pack("<3f", *vertex.normal.as_tuple()))
        blob.extend(struct.pack("<4B", *vertex.color))
        blob.extend(struct.pack("<2f", *vertex.uv))
    return bytes(blob)
