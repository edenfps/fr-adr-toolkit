"""glTF 2.0 importer for skinned meshes."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from pygltflib import GLTF2

from .dme import SkinnedVertex, Vec3
from .import_obj import ImportedMesh


@dataclass
class ImportedAnimation:
    name: str
    duration: float
    channels: list[dict] = field(default_factory=list)


@dataclass
class ImportedGltf:
    mesh: ImportedMesh
    animations: list[ImportedAnimation] = field(default_factory=list)


def load_gltf(path: Path) -> ImportedGltf:
    gltf = GLTF2().load(str(path))
    blob = _primary_blob(gltf, path.parent)

    mesh = gltf.meshes[0]
    primitive = mesh.primitives[0]
    positions = _accessor_vec3(gltf, blob, primitive.attributes.POSITION)
    normals = (
        _accessor_vec3(gltf, blob, primitive.attributes.NORMAL)
        if primitive.attributes.NORMAL is not None
        else [(0.0, 1.0, 0.0) for _ in positions]
    )
    uvs = (
        _accessor_vec2(gltf, blob, primitive.attributes.TEXCOORD_0)
        if primitive.attributes.TEXCOORD_0 is not None
        else [(0.0, 0.0) for _ in positions]
    )
    indices = _accessor_indices(gltf, blob, primitive.indices)

    skin = gltf.skins[0] if gltf.skins else None
    bone_names = ["ROOT"]
    joint_indices = [(0, 0, 0, 0) for _ in positions]
    joint_weights = [(1.0, 0.0, 0.0, 0.0) for _ in positions]

    if skin is not None:
        bone_names = [gltf.nodes[joint].name or f"BONE_{joint}" for joint in skin.joints]
        weights = _accessor_vec4(gltf, blob, primitive.attributes.WEIGHTS_0)
        joints = _accessor_joint_indices(gltf, blob, primitive.attributes.JOINTS_0)
        joint_weights = [(w[0], w[1], w[2], 0.0) for w in weights]
        joint_indices = joints

    imported = ImportedMesh(bone_names=bone_names)
    for index, position in enumerate(positions):
        weights = joint_weights[index]
        joints = joint_indices[index]
        imported.vertices.append(
            SkinnedVertex(
                position=Vec3(*position),
                bone_weights=(weights[0], weights[1], weights[2]),
                bone_indices=(joints[0], joints[1], joints[2], joints[3]),
                normal=Vec3(*normals[index]),
                color=(128, 128, 128, 255),
                uv=uvs[index],
            )
        )
    imported.indices = indices

    animations: list[ImportedAnimation] = []
    for animation in gltf.animations or []:
        channels = []
        duration = 0.0
        for channel in animation.channels:
            sampler = animation.samplers[channel.sampler]
            times = _accessor_floats(gltf, blob, sampler.input)
            values = _accessor_values(gltf, blob, sampler.output)
            if times:
                duration = max(duration, times[-1])
            channels.append(
                {
                    "target_node": channel.target.node,
                    "target_path": channel.target.path,
                    "times": times,
                    "values": values,
                }
            )
        animations.append(
            ImportedAnimation(
                name=animation.name or "animation",
                duration=duration,
                channels=channels,
            )
        )

    return ImportedGltf(mesh=imported, animations=animations)


def _primary_blob(gltf: GLTF2, base_dir: Path) -> bytes:
    if not gltf.buffers:
        raise ValueError("glTF file has no buffers")

    buffer = gltf.buffers[0]
    if buffer.uri:
        uri = buffer.uri
        if uri.startswith("data:"):
            data = gltf.get_data_from_buffer_uri(uri)
            if data is None:
                raise ValueError("Embedded data URI buffer could not be decoded")
            return data
        external = base_dir / uri
        if not external.is_file():
            raise FileNotFoundError(f"glTF external buffer not found: {external}")
        return external.read_bytes()

    blob = gltf.binary_blob()
    if blob is not None:
        return blob

    raise ValueError(
        "glTF buffer has no URI and no embedded GLB binary data. "
        "Re-export as a single .glb file, or keep the .bin next to the .gltf."
    )


def _accessor_data(gltf: GLTF2, blob: bytes, accessor_index: int):
    accessor = gltf.accessors[accessor_index]
    buffer_view = gltf.bufferViews[accessor.bufferView]
    start = (buffer_view.byteOffset or 0) + (accessor.byteOffset or 0)
    end = start + _component_length(accessor) * accessor.count
    return blob[start:end], accessor


def _component_length(accessor) -> int:
    mapping = {
        "SCALAR": 1,
        "VEC2": 2,
        "VEC3": 3,
        "VEC4": 4,
    }
    comp = mapping[accessor.type]
    if accessor.componentType == 5126:
        return comp * 4
    if accessor.componentType == 5123:
        return comp * 2
    if accessor.componentType == 5125:
        return comp * 4
    if accessor.componentType in (5121,):
        return comp
    raise ValueError(f"Unsupported component type {accessor.componentType}")


def _unpack(accessor, data: bytes):
    if accessor.componentType == 5126:
        count = accessor.count * {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor.type]
        return list(struct.unpack(f"<{count}f", data))
    if accessor.componentType == 5123:
        count = accessor.count * {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor.type]
        return list(struct.unpack(f"<{count}H", data))
    if accessor.componentType == 5125:
        count = accessor.count * {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor.type]
        return list(struct.unpack(f"<{count}I", data))
    if accessor.componentType == 5121:
        return list(data)
    raise ValueError(f"Unsupported component type {accessor.componentType}")


def _group(values, size: int):
    return [tuple(values[i : i + size]) for i in range(0, len(values), size)]


def _accessor_vec3(gltf, blob, index):
    data, accessor = _accessor_data(gltf, blob, index)
    return _group(_unpack(accessor, data), 3)


def _accessor_vec2(gltf, blob, index):
    data, accessor = _accessor_data(gltf, blob, index)
    return _group(_unpack(accessor, data), 2)


def _accessor_vec4(gltf, blob, index):
    data, accessor = _accessor_data(gltf, blob, index)
    return _group(_unpack(accessor, data), 4)


def _accessor_joint_indices(gltf, blob, index):
    data, accessor = _accessor_data(gltf, blob, index)
    values = _unpack(accessor, data)
    return _group(values, 4)


def _accessor_indices(gltf, blob, index):
    data, accessor = _accessor_data(gltf, blob, index)
    return _unpack(accessor, data)


def _accessor_floats(gltf, blob, index):
    data, accessor = _accessor_data(gltf, blob, index)
    return _unpack(accessor, data)


def _accessor_values(gltf, blob, index):
    data, accessor = _accessor_data(gltf, blob, index)
    values = _unpack(accessor, data)
    if accessor.type == "VEC3":
        return _group(values, 3)
    if accessor.type == "VEC4":
        return _group(values, 4)
    return values
