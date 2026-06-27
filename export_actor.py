#!/usr/bin/env python3
"""Export a ForgeLight actor folder to intermediate files for DCC tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fr_formats import AdrFile, DmeFile, DskFile


def export_obj(mesh: DmeFile, output_path: Path) -> None:
    lines: list[str] = ["# ForgeLight mesh export", f"o {output_path.stem}"]
    vertex_offset = 1
    for chunk_index, chunk in enumerate(mesh.meshes):
        lines.append(f"g mesh_{chunk_index}")
        for vertex in chunk.vertices:
            lines.append(
                f"v {vertex.position.x:.6f} {vertex.position.y:.6f} {vertex.position.z:.6f}"
            )
        for vertex in chunk.vertices:
            lines.append(
                f"vt {vertex.uv[0]:.6f} {vertex.uv[1]:.6f}"
            )
        for vertex in chunk.vertices:
            lines.append(
                f"vn {vertex.normal.x:.6f} {vertex.normal.y:.6f} {vertex.normal.z:.6f}"
            )
        for triangle_index in range(0, len(chunk.indices), 3):
            i0, i1, i2 = (
                chunk.indices[triangle_index] + vertex_offset,
                chunk.indices[triangle_index + 1] + vertex_offset,
                chunk.indices[triangle_index + 2] + vertex_offset,
            )
            lines.append(f"f {i0}/{i0}/{i0} {i1}/{i1}/{i1} {i2}/{i2}/{i2}")
        vertex_offset += len(chunk.vertices)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_skin_json(mesh: DmeFile, output_path: Path) -> None:
    payload = []
    for chunk_index, chunk in enumerate(mesh.meshes):
        payload.append(
            {
                "mesh_index": chunk_index,
                "material_index": chunk.material_index,
                "vertices": [
                    {
                        "position": vertex.position.as_tuple(),
                        "normal": vertex.normal.as_tuple(),
                        "uv": vertex.uv,
                        "bone_indices": vertex.bone_indices,
                        "bone_weights": vertex.bone_weights,
                    }
                    for vertex in chunk.vertices
                ],
                "indices": chunk.indices,
            }
        )
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def export_skeleton_json(skeleton: DskFile, output_path: Path) -> None:
    payload = {
        "version": skeleton.version,
        "bones": [
            {
                "index": index,
                "name": name,
                "bind_pose": skeleton.bind_pose_matrices[index],
            }
            for index, name in enumerate(skeleton.bone_names)
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("actor_dir", type=Path, help="Folder containing .adr and related files")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory (defaults to actor_dir/export)",
    )
    args = parser.parse_args()

    actor_dir = args.actor_dir
    output_dir = args.output or (actor_dir / "export")
    output_dir.mkdir(parents=True, exist_ok=True)

    adr_files = list(actor_dir.glob("*.adr"))
    if not adr_files:
        raise SystemExit(f"No .adr file found in {actor_dir}")
    adr = AdrFile.load(adr_files[0])

    summary = {
        "skeleton_file": adr.skeleton_file,
        "mesh_file": adr.mesh_file,
        "material_file": adr.material_file,
        "model_scale": adr.model_scale,
        "animation_count": len(adr.locomotion_animations),
        "animations": [
            {
                "slot": animation.slot_name,
                "file": animation.gr2_file,
                "speed": animation.speed,
            }
            for animation in adr.locomotion_animations
        ],
        "foley_slots": adr.foley_slots,
    }
    (output_dir / "actor.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if adr.skeleton_file:
        skeleton_path = actor_dir / adr.skeleton_file
        if skeleton_path.exists():
            export_skeleton_json(DskFile.load(skeleton_path), output_dir / "skeleton.json")

    if adr.mesh_file:
        mesh_path = actor_dir / adr.mesh_file
        if mesh_path.exists():
            mesh = DmeFile.load(mesh_path)
            export_obj(mesh, output_dir / f"{mesh_path.stem}.obj")
            export_skin_json(mesh, output_dir / f"{mesh_path.stem}_skin.json")

    print(f"Exported actor data to {output_dir}")


if __name__ == "__main__":
    main()
