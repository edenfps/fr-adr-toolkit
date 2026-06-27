"""Wavefront OBJ importer with optional skin sidecar JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .dme import SkinnedVertex, Vec3


@dataclass
class ImportedMesh:
    vertices: list[SkinnedVertex] = field(default_factory=list)
    indices: list[int] = field(default_factory=list)
    bone_names: list[str] = field(default_factory=lambda: ["ROOT"])


def load_obj(path: Path, skin_json: Path | None = None) -> ImportedMesh:
    if skin_json is None:
        for candidate in (
            path.with_suffix(".skin.json"),
            path.with_name(f"{path.stem}_skin.json"),
        ):
            if candidate.exists():
                skin_json = candidate
                break

    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    faces: list[tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = []

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        tag = parts[0]
        if tag == "v" and len(parts) >= 4:
            positions.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif tag == "vn" and len(parts) >= 4:
            normals.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif tag == "vt" and len(parts) >= 3:
            uvs.append((float(parts[1]), float(parts[2])))
        elif tag == "f" and len(parts) >= 4:
            corners = [_parse_face_corner(corner, len(positions), len(uvs), len(normals)) for corner in parts[1:4]]
            faces.append((corners[0], corners[1], corners[2]))

    skin = _load_skin_sidecar(skin_json) if skin_json else None
    mesh = ImportedMesh()
    mesh.bone_names = skin.get("bone_names", ["ROOT"]) if skin else ["ROOT"]

    corner_to_index: dict[tuple[int, int, int], int] = {}
    for face in faces:
        triangle: list[int] = []
        for position_index, uv_index, normal_index in face:
            key = (position_index, uv_index, normal_index)
            vertex_index = corner_to_index.get(key)
            if vertex_index is None:
                vertex_index = len(mesh.vertices)
                corner_to_index[key] = vertex_index
                mesh.vertices.append(
                    _vertex_from_corner(
                        positions,
                        normals,
                        uvs,
                        skin,
                        position_index,
                        uv_index,
                        normal_index,
                    )
                )
            triangle.append(vertex_index)
        mesh.indices.extend(triangle)

    if not mesh.vertices:
        raise ValueError(f"No geometry found in {path}")
    return mesh


def _parse_face_corner(
    corner: str,
    position_count: int,
    uv_count: int,
    normal_count: int,
) -> tuple[int, int, int]:
    parts = corner.split("/")
    position_index = _index(int(parts[0]), position_count) if parts[0] else 0
    uv_index = _index(int(parts[1]), uv_count) if len(parts) > 1 and parts[1] else position_index
    normal_index = _index(int(parts[2]), normal_count) if len(parts) > 2 and parts[2] else position_index
    return position_index, uv_index, normal_index


def _vertex_from_corner(
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
    uvs: list[tuple[float, float]],
    skin: dict | None,
    position_index: int,
    uv_index: int,
    normal_index: int,
) -> SkinnedVertex:
    pos = positions[position_index]
    normal = normals[normal_index] if 0 <= normal_index < len(normals) else (0.0, 1.0, 0.0)
    uv = uvs[uv_index] if 0 <= uv_index < len(uvs) else (0.0, 0.0)
    weights, indices = _skin_for_vertex(skin, position_index)
    return SkinnedVertex(
        position=Vec3(*pos),
        bone_weights=weights,
        bone_indices=indices,
        normal=Vec3(*normal),
        color=(128, 128, 128, 255),
        uv=uv,
    )


def _index(raw: int, count: int) -> int:
    if raw > 0:
        return raw - 1
    return count + raw


def _load_skin_sidecar(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        if not payload:
            return {}
        return payload[0]
    return payload


def _skin_for_vertex(
    skin: dict | None,
    vertex_index: int,
) -> tuple[tuple[float, float, float], tuple[int, int, int, int]]:
    if skin and "vertices" in skin:
        entries = skin["vertices"]
        if vertex_index < len(entries):
            entry = entries[vertex_index]
            indices = tuple(entry.get("bone_indices", [0, 0, 0, 0]))
            weights = entry.get("bone_weights", [1.0, 0.0, 0.0])
            padded = list(indices) + [0, 0, 0, 0]
            w = list(weights) + [0.0, 0.0, 0.0]
            return (w[0], w[1], w[2]), (
                padded[0],
                padded[1],
                padded[2],
                padded[3],
            )
    return (1.0, 0.0, 0.0), (0, 0, 0, 0)
