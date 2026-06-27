#!/usr/bin/env python3
"""
Convert a generic 3D model (OBJ or glTF) into Free Realms actor assets.

Loose-file replacement (default) — drop output over the client folder to override chatdy:

    python convert_to_fr.py --input myfox.obj --texture myfox.dds

Player body (human_m) — mesh file is human_m_body_lod0.dme, not human_m_lod0.dme:

    python convert_to_fr.py --replace human_m --template templates/human_m --input model.obj --mesh-only

Prop / NPC full bundle (adr + dme + dma + dsk + dds), e.g. warpstone model id 280:

    python convert_to_fr.py --replace sg_warpstone_01 --template templates/sg_warpstone_01 --input model.obj

Custom actor name (separate file set):

    python convert_to_fr.py --no-replace --name myfox --input myfox.obj
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from fr_formats import AdrFile, DmaFile, DmeFile
from fr_formats.dme import MeshChunk, Vec3
from fr_formats.import_obj import ImportedMesh, load_obj
from fr_formats.writers import (
    write_adr_minimal,
    write_adr_preserve_template,
    write_dma,
    write_dma_hybrid,
    write_dme,
    write_dsk,
)


def is_fr_binary_adr(path: Path) -> bool:
    """True for Free Realms binary .adr files (not H1Z1/XML)."""
    try:
        head = path.read_bytes()[:32]
    except OSError:
        return False
    if head.startswith((b"<?", b"<ActorRuntime", b"<")):
        return False
    return path.suffix.lower() == ".adr"


def list_fr_actors(source_dir: Path) -> list[str]:
    """Return basenames of Free Realms binary .adr files in a folder."""
    if not source_dir.is_dir():
        return []
    actors = [path.stem for path in source_dir.glob("*.adr") if is_fr_binary_adr(path)]
    return sorted(set(actors))


def _resolve_template_adr_path(template_dir: Path, actor: str | None) -> Path:
    if actor:
        named = template_dir / f"{actor}.adr"
        if named.is_file():
            return named

    adrs = [path for path in template_dir.glob("*.adr") if is_fr_binary_adr(path)]
    if len(adrs) == 1:
        return adrs[0]
    if actor:
        raise FileNotFoundError(f"Template ADR not found for actor '{actor}' in {template_dir}")
    if not adrs:
        raise FileNotFoundError(f"No Free Realms .adr templates found in {template_dir}")
    raise ValueError(
        f"Multiple ADR files ({len(adrs)}) in {template_dir}. "
        "Select a target actor or use a single-actor template folder."
    )


@dataclass
class ActorNaming:
    """Output filenames for an actor bundle."""

    actor: str
    adr_file: str
    mesh_file: str
    dma_file: str
    texture_file: str
    texture_dma_name: str
    skeleton_file: str
    gr2_prefix: str

    @classmethod
    def from_template(cls, actor: str, template: AdrFile, dma: DmaFile) -> ActorNaming:
        texture_dma_name = dma.textures[0] if dma.textures else f"{actor.upper()}.DDS"
        return cls(
            actor=actor,
            adr_file=f"{actor}.adr",
            mesh_file=template.mesh_file or f"{actor}_lod0.dme",
            dma_file=template.material_file or f"{actor}.dma",
            texture_file=texture_dma_name.lower(),
            texture_dma_name=texture_dma_name,
            skeleton_file=template.skeleton_file or "treeble.dsk",
            gr2_prefix=f"{actor}_",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Source .obj, .gltf, or .glb")
    parser.add_argument(
        "--replace",
        default="chatdy",
        metavar="ACTOR",
        help="Emit exact filenames for this actor so loose files override the game asset (default: chatdy)",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="Write a new actor name instead of overriding an existing one",
    )
    parser.add_argument("--name", help="Basename when using --no-replace (e.g. myfox)")
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "chatdy",
        help="Reference actor folder (default: chatdy)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory (default: output/<actor>/)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=None,
        help="Actor scale in .adr (default: keep template scale when replacing)",
    )
    parser.add_argument(
        "--skeleton",
        choices=("treeble", "generated"),
        default="treeble",
        help="treeble = reuse template skeleton so existing animations still work",
    )
    parser.add_argument(
        "--copy-animations",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Copy template .gr2 files into output (default: off when replacing, on for new actors)",
    )
    parser.add_argument(
        "--texture",
        type=Path,
        help="Optional .dds texture file for the model",
    )
    parser.add_argument("--pack", action="store_true", help="Also write zlib-compressed .z files")
    parser.add_argument(
        "--write-adr",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Write .adr (default: on when replacing props/NPCs, off for human_m player body). "
        "Use --no-write-adr for human_m mesh-only swaps.",
    )
    parser.add_argument(
        "--mesh-scale",
        type=float,
        default=1.0,
        help="Uniform scale applied to input vertex positions before writing the DME",
    )
    parser.add_argument(
        "--mesh-offset",
        type=float,
        nargs=3,
        metavar=("X", "Y", "Z"),
        default=(0.0, 0.0, 0.0),
        help="Translation applied after --mesh-scale (game units)",
    )
    parser.add_argument(
        "--preserve-extra-meshes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep extra DME sub-meshes from the template (default: on). "
        "Warpstone needs this for visibility; use --no-preserve-extra-meshes to drop FX geometry.",
    )
    parser.add_argument(
        "--fit-template",
        action="store_true",
        help="Scale and center the input mesh to match the template's primary mesh bounds",
    )
    parser.add_argument(
        "--mesh-only",
        action="store_true",
        help="Only write the mesh .dme (safest loose override for player actors)",
    )
    return parser.parse_args()


def _load_template_assets(
    template_dir: Path,
    actor: str | None = None,
) -> tuple[Path, AdrFile, bytes, DmaFile, DmeFile]:
    template_adr_path = _resolve_template_adr_path(template_dir, actor)
    adr_template = AdrFile.load(template_adr_path)
    template_adr_bytes = template_adr_path.read_bytes()

    dma_name = adr_template.material_file
    if not dma_name:
        raise FileNotFoundError(f"Template ADR {template_adr_path.name} has no material file")
    dma_path = template_dir / dma_name
    if not dma_path.is_file():
        raise FileNotFoundError(f"Template DMA not found: {dma_path}")
    dma_template = DmaFile.load(dma_path)

    mesh_name = adr_template.mesh_file
    if not mesh_name:
        raise FileNotFoundError(f"Template ADR {template_adr_path.name} has no mesh file")
    mesh_path = template_dir / mesh_name
    if not mesh_path.is_file():
        raise FileNotFoundError(f"Template mesh not found: {mesh_path}")
    dme_template = DmeFile.load(mesh_path)

    return template_adr_path, adr_template, template_adr_bytes, dma_template, dme_template


def convert_assets(args: argparse.Namespace) -> dict:
    """Convert input mesh to Free Realms actor assets. Returns install manifest."""
    template_dir = args.template.resolve()
    template_actor = None if args.no_replace else args.replace
    template_adr_path, adr_template, adr_template_bytes, dma_template, dme_template = (
        _load_template_assets(template_dir, template_actor)
    )

    if args.no_replace:
        if not args.name:
            raise SystemExit("--name is required when using --no-replace")
        actor = args.name
        naming = ActorNaming.from_template(actor, adr_template, dma_template)
        copy_animations = True if args.copy_animations is None else args.copy_animations
    else:
        actor = args.replace
        naming = ActorNaming.from_template(actor, adr_template, dma_template)
        copy_animations = False if args.copy_animations is None else args.copy_animations

    model_scale = args.scale if args.scale is not None else (adr_template.model_scale or 1.0)
    output_dir = (args.output or (Path("output") / actor)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.mesh_only:
        for stale in (
            naming.adr_file,
            naming.dma_file,
            naming.skeleton_file,
            naming.texture_file,
        ):
            stale_path = output_dir / stale
            if stale_path.exists():
                stale_path.unlink()

    mesh_data = _load_input(args.input) if not getattr(args, "input_mesh_chunks", None) else _mesh_data_from_chunks(
        args.input_mesh_chunks
    )
    template_mesh = dme_template.meshes[0] if dme_template.meshes else None
    if args.fit_template and template_mesh:
        _fit_mesh_to_template(mesh_data, template_mesh)
    _transform_mesh(mesh_data, args.mesh_scale, args.mesh_offset)
    mesh_unknown = template_mesh.unknown if template_mesh else None
    trailing_template = dme_template.trailing_bytes if dme_template.trailing_bytes else None
    template_vertex_count = len(template_mesh.vertices) if template_mesh else None
    template_index_count = len(template_mesh.indices) if template_mesh else None
    write_adr = (not args.no_replace and args.write_adr is not False and not args.mesh_only) or (
        args.no_replace and args.write_adr is not False
    )
    if not args.no_replace and args.replace == "human_m" and args.write_adr is None:
        write_adr = False

    h1z1_texture_dma = getattr(args, "h1z1_texture_dma", None)
    use_h1z1_textures = h1z1_texture_dma is not None or getattr(args, "dma_material_template", None) is not None

    if args.mesh_only:
        dma_path = template_dir / naming.dma_file
        if not dma_path.exists():
            dma_path = next(template_dir.glob("*.dma"))
        dma_bytes = dma_path.read_bytes()
    else:
        if getattr(args, "dma_material_template", None) is not None:
            material_template = args.dma_material_template
            texture_names = getattr(args, "h1z1_texture_names", None) or material_template.textures
            write_dma_hybrid(
                output_dir / naming.dma_file,
                DmaFile(textures=list(texture_names), materials=list(material_template.materials)),
                material_template,
                texture_names=texture_names,
            )
            dma_bytes = (output_dir / naming.dma_file).read_bytes()
        elif h1z1_texture_dma is not None:
            write_dma_hybrid(
                output_dir / naming.dma_file,
                h1z1_texture_dma,
                dma_template,
                texture_names=getattr(args, "h1z1_texture_names", None),
            )
            dma_bytes = (output_dir / naming.dma_file).read_bytes()
        else:
            write_dma(
                output_dir / naming.dma_file,
                naming.texture_dma_name,
                template=dma_template,
            )
            dma_bytes = (output_dir / naming.dma_file).read_bytes()

        if args.skeleton == "treeble":
            shutil.copy2(template_dir / naming.skeleton_file, output_dir / naming.skeleton_file)
        else:
            naming.skeleton_file = f"{actor}.dsk"
            write_dsk(
                output_dir / naming.skeleton_file,
                mesh_data.bone_names,
                hierarchy_template=template_dir / (adr_template.skeleton_file or "treeble.dsk"),
            )

        if not use_h1z1_textures:
            _write_texture(args.texture, template_dir, output_dir, naming)

    input_mesh_chunks = getattr(args, "input_mesh_chunks", None)
    if input_mesh_chunks:
        dme_meshes = input_mesh_chunks
        use_template_trailing = False
    else:
        dme_meshes = _build_output_meshes(
            mesh_data,
            dme_template,
            mesh_unknown,
            preserve_extra_meshes=args.preserve_extra_meshes,
        )
        use_template_trailing = bool(
            trailing_template
            and args.preserve_extra_meshes
            and len(dme_template.meshes) > 1
        )

    write_dme(
        output_dir / naming.mesh_file,
        mesh_data.vertices,
        mesh_data.indices,
        dma_bytes,
        trailing_template=trailing_template,
        mesh_unknown=mesh_unknown,
        template_vertex_count=template_vertex_count,
        template_index_count=template_index_count,
        auto_trailing=not use_template_trailing,
        meshes=dme_meshes,
    )

    if write_adr:
        animations = _template_animations(adr_template) if copy_animations else []
        if copy_animations:
            _copy_gr2_files(template_dir, output_dir, adr_template, naming.gr2_prefix)

        if adr_template.raw_sections and any(
            section_type not in (1, 2) for section_type, _ in adr_template.raw_sections
        ):
            write_adr_preserve_template(
                output_dir / naming.adr_file,
                adr_template_bytes,
                naming.skeleton_file,
                naming.mesh_file,
                naming.dma_file,
                model_scale,
            )
        else:
            write_adr_minimal(
                output_dir / naming.adr_file,
                naming.skeleton_file,
                naming.mesh_file,
                naming.dma_file,
                animations,
                model_scale=model_scale,
            )

    manifest = {
        "mode": "replace" if not args.no_replace else "new_actor",
        "actor": actor,
        "output_dir": str(output_dir),
        "files_written": sorted(p.name for p in output_dir.iterdir() if p.is_file()),
        "skeleton_mode": args.skeleton,
        "copy_animations": copy_animations,
        "write_adr": write_adr,
        "mesh_only": args.mesh_only,
        "dme_trailing": (
            "template_multibatch"
            if mesh_unknown and mesh_unknown[0] > 1
            else "auto_single_batch"
        ),
        "notes": _install_notes(
            args, naming, mesh_data, copy_animations, mesh_unknown, write_adr
        ),
    }
    (output_dir / "install.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.pack:
        _pack_directory(output_dir)

    return manifest


def main() -> None:
    args = parse_args()
    manifest = convert_assets(args)
    actor = manifest["actor"]
    output_dir = Path(manifest["output_dir"])

    print(f"Wrote {actor} assets to {output_dir}")
    if manifest["mode"] == "replace":
        print()
        print("Loose-file install: copy these files into your Free Realms client folder")
        print(
            f"(same paths the game loads for {actor} - unpacked files override archive assets)."
        )
    print()
    for line in manifest["notes"]:
        print(f"  - {line}")


def _load_input(path: Path) -> ImportedMesh:
    suffix = path.suffix.lower()
    if suffix == ".obj":
        return load_obj(path)
    if suffix in {".gltf", ".glb"}:
        try:
            from fr_formats.import_gltf import load_gltf
        except ImportError as exc:
            raise SystemExit(
                "glTF support requires pygltflib. Install dependencies with:\n"
                "  python -m pip install -r requirements.txt"
            ) from exc
        return load_gltf(path).mesh
    raise SystemExit(f"Unsupported input format: {path.suffix}")


def _transform_mesh(
    mesh: ImportedMesh,
    scale: float,
    offset: tuple[float, float, float],
) -> None:
    if scale == 1.0 and offset == (0.0, 0.0, 0.0):
        return
    ox, oy, oz = offset
    for vertex in mesh.vertices:
        vertex.position = Vec3(
            vertex.position.x * scale + ox,
            vertex.position.y * scale + oy,
            vertex.position.z * scale + oz,
        )


def _mesh_data_from_chunks(chunks: list[MeshChunk]) -> ImportedMesh:
    mesh = ImportedMesh(bone_names=["ROOT"])
    for chunk in chunks:
        offset = len(mesh.vertices)
        mesh.vertices.extend(chunk.vertices)
        mesh.indices.extend(index + offset for index in chunk.indices)
    return mesh


def _build_output_meshes(
    mesh_data: ImportedMesh,
    dme_template: DmeFile,
    mesh_unknown: tuple[int, int, int] | None,
    preserve_extra_meshes: bool,
) -> list[MeshChunk]:
    primary = MeshChunk(
        material_index=dme_template.meshes[0].material_index if dme_template.meshes else 0,
        unknown=mesh_unknown or (dme_template.meshes[0].unknown if dme_template.meshes else (1, 24, -1)),
        vertices=mesh_data.vertices,
        indices=mesh_data.indices,
        vertex_stride=dme_template.meshes[0].vertex_stride if dme_template.meshes else 52,
    )
    if len(dme_template.meshes) <= 1 or not preserve_extra_meshes:
        return [primary]

    output: list[MeshChunk] = [primary]
    output.extend(dme_template.meshes[1:])
    return output


def _fit_mesh_to_template(mesh: ImportedMesh, template: MeshChunk) -> None:
    def bounds(vertices):
        xs = [vertex.position.x for vertex in vertices]
        ys = [vertex.position.y for vertex in vertices]
        zs = [vertex.position.z for vertex in vertices]
        return (
            Vec3(min(xs), min(ys), min(zs)),
            Vec3(max(xs), max(ys), max(zs)),
        )

    source_min, source_max = bounds(mesh.vertices)
    target_min, target_max = bounds(template.vertices)
    source_size = max(
        source_max.x - source_min.x,
        source_max.y - source_min.y,
        source_max.z - source_min.z,
    )
    target_size = max(
        target_max.x - target_min.x,
        target_max.y - target_min.y,
        target_max.z - target_min.z,
    )
    if source_size <= 0 or target_size <= 0:
        return

    scale = target_size / source_size
    source_center = Vec3(
        (source_min.x + source_max.x) * 0.5,
        (source_min.y + source_max.y) * 0.5,
        (source_min.z + source_max.z) * 0.5,
    )
    target_center = Vec3(
        (target_min.x + target_max.x) * 0.5,
        (target_min.y + target_max.y) * 0.5,
        (target_min.z + target_max.z) * 0.5,
    )
    for vertex in mesh.vertices:
        vertex.position = Vec3(
            (vertex.position.x - source_center.x) * scale + target_center.x,
            (vertex.position.y - source_center.y) * scale + target_center.y,
            (vertex.position.z - source_center.z) * scale + target_center.z,
        )


def _template_animations(template: AdrFile) -> list[tuple[str, str, float]]:
    animations: list[tuple[str, str, float]] = []
    for animation in template.locomotion_animations:
        speed = animation.speed if animation.speed is not None else 1.0
        animations.append((animation.slot_name, animation.gr2_file, speed))
    return animations


def _copy_gr2_files(
    template_dir: Path,
    output_dir: Path,
    template: AdrFile,
    gr2_prefix: str,
) -> None:
    copied: set[str] = set()
    for animation in template.locomotion_animations:
        source_name = animation.gr2_file
        if source_name in copied:
            continue
        source_path = template_dir / source_name
        if source_path.exists():
            shutil.copy2(source_path, output_dir / source_name)
            copied.add(source_name)


def _write_texture(
    texture_path: Path | None,
    template_dir: Path,
    output_dir: Path,
    naming: ActorNaming,
) -> None:
    target = output_dir / naming.texture_file
    if texture_path and texture_path.exists():
        shutil.copy2(texture_path, target)
        return
    named = template_dir / naming.texture_dma_name
    if named.exists():
        shutil.copy2(named, target)
        return
    for candidate in template_dir.glob("*.dds"):
        shutil.copy2(candidate, target)
        return
    target.write_bytes(_minimal_dds())


def _minimal_dds() -> bytes:
    header = bytearray(128)
    header[0:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x000A1007)
    struct.pack_into("<I", header, 12, 4)
    struct.pack_into("<I", header, 16, 4)
    struct.pack_into("<I", header, 20, 8)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 0x41)
    struct.pack_into("<I", header, 84, 4)
    struct.pack_into("<I", header, 88, 0x20)
    struct.pack_into("<I", header, 108, 0x1000)
    return bytes(header) + (b"\xFF\x88\x44\xFF" * 16)


def _pack_directory(output_dir: Path) -> None:
    for path in output_dir.iterdir():
        if path.suffix == ".z" or path.name == "install.json":
            continue
        if path.is_file():
            (output_dir / f"{path.name}.z").write_bytes(zlib.compress(path.read_bytes()))


def _install_notes(
    args: argparse.Namespace,
    naming: ActorNaming,
    mesh: ImportedMesh,
    copy_animations: bool,
    mesh_unknown: tuple[int, int, int] | None,
    write_adr: bool,
) -> list[str]:
    if not args.no_replace:
        notes = [
            f"Override target: {naming.actor}",
            "Typical loose override: copy the full bundle from this folder "
            f"({naming.adr_file}, {naming.mesh_file}, {naming.dma_file}, "
            f"{naming.texture_file}, {naming.skeleton_file}).",
            "Texture-only swaps can use just the .dds file.",
        ]
        if naming.actor == "human_m":
            notes.append(
                "human_m player body: prefer --mesh-only and do NOT copy a rewritten .adr "
                "(it drops skintone sections)."
            )
        if mesh_unknown and mesh_unknown[0] > 1:
            notes.append(
                f"Template uses {mesh_unknown[0]} render batches; trailing metadata was cloned from "
                f"the template DME so the client accepts the file."
            )
        if args.pack or naming.actor == "human_m":
            notes.append(
                f"If the override still fails, delete any cached {naming.mesh_file}.z from the "
                "client asset cache so the loose .dme is picked up."
            )
        if args.mesh_only:
            notes.append(
                f"Mesh-only mode: only {naming.mesh_file} was written. "
                f"Do not copy {naming.adr_file} from older converter output."
            )
        elif not write_adr:
            notes.append(
                f"{naming.adr_file} was NOT written. For player actors (human_m), "
                "copying a broken .adr causes 'failed to find local player actor'."
            )
        else:
            notes.append(
                f"{naming.adr_file} was written with all non-core template sections preserved."
            )
    else:
        notes = [
            f"New actor bundle written as {naming.actor}.*",
            "Register in Models.txt or use loose files if the client resolves these names.",
        ]

    if args.skeleton == "treeble":
        notes.append(
            f"Mesh should be weighted to {naming.skeleton_file} bones so existing animations deform correctly."
        )
    else:
        notes.append(
            "Custom skeleton: existing template .gr2 animations will not match this rig."
        )

    if not copy_animations and not args.no_replace:
        notes.append(
            f"Animations not copied - game keeps using its existing {naming.gr2_prefix}*.gr2 loose/archive files."
        )

    if len(mesh.bone_names) > 1:
        notes.append(f"Input rig: {len(mesh.bone_names)} bones.")
    elif not args.no_replace:
        notes.append(
            f"Input has no skin weights - vertices bind to ROOT; retarget to {naming.skeleton_file} in Blender for animation."
        )

    return notes


if __name__ == "__main__":
    main()
