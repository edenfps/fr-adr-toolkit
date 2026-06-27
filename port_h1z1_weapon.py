#!/usr/bin/env python3
"""Port an H1Z1 ForgeLight weapon/prop into a Free Realms loose-file override."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from convert_to_fr import ActorNaming, convert_assets, _load_template_assets, _pack_directory
from export_actor import export_obj
from fr_formats import DmeFile
from fr_formats.h1z1_adr import H1Z1Actor, resolve_h1z1_diffuse_path
from fr_formats.import_obj import ImportedMesh


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Folder containing extracted H1Z1 assets",
    )
    parser.add_argument(
        "--actor",
        default="Weapons_PumpShotgun01_3P",
        help="H1Z1 actor basename (default: Weapons_PumpShotgun01_3P)",
    )
    parser.add_argument(
        "--replace",
        default="sg_warpstone_01",
        help="Free Realms actor to override (default: sg_warpstone_01)",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).resolve().parent / "templates" / "sg_warpstone_01",
        help="Free Realms template actor folder",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output folder (default: output/sg_warpstone_01_loose/<actor>)",
    )
    parser.add_argument(
        "--lod",
        type=int,
        default=0,
        help="H1Z1 LOD index to port (default: 0)",
    )
    parser.add_argument(
        "--no-fit-template",
        action="store_true",
        help="Do not scale/center mesh to the Free Realms template bounds",
    )
    parser.add_argument(
        "--no-preserve-extra-meshes",
        action="store_true",
        help="Drop warpstone FX/crystal sub-meshes (usually keep them for visibility)",
    )
    parser.add_argument(
        "--pack",
        action="store_true",
        help="Also write compressed .z files",
    )
    parser.add_argument(
        "--export-preview",
        action="store_true",
        help="Also export intermediate OBJ preview files",
    )
    return parser.parse_args()


def list_h1z1_actors(source_dir: Path) -> list[str]:
    """Return basenames of H1Z1 XML ActorRuntime .adr files in a folder."""
    actors: list[str] = []
    if not source_dir.is_dir():
        return actors
    for path in source_dir.glob("*.adr"):
        try:
            if path.read_bytes()[:32].startswith(b"<ActorRuntime"):
                actors.append(path.stem)
        except OSError:
            continue
    return sorted(actors)


def _mesh_file_for_lod(actor: H1Z1Actor, lod: int) -> str:
    if lod <= 0:
        return actor.mesh_file
    if lod - 1 < len(actor.lods):
        return actor.lods[lod - 1].mesh_file
    raise ValueError(f"LOD {lod} not available for {actor.mesh_file}")


def _build_fr_texture_slots(
    fr_textures: list[str],
) -> list[str]:
    """Always use the Free Realms template DMA texture names (shader binds slot 0)."""
    if fr_textures:
        return list(fr_textures)
    return ["SG_WARPSTONE_01.DDS", "SG_WARPSTONE_01.DDS"]


def _dme_to_imported_mesh(dme: DmeFile) -> ImportedMesh:
    imported = ImportedMesh(bone_names=["ROOT"])
    vertex_offset = 0
    for chunk in dme.meshes:
        imported.vertices.extend(chunk.vertices)
        imported.indices.extend(index + vertex_offset for index in chunk.indices)
        vertex_offset += len(chunk.vertices)
    return imported


def _write_temp_obj(mesh: ImportedMesh, path: Path) -> None:
    lines = ["# H1Z1 port intermediate mesh", f"o {path.stem}"]
    for vertex in mesh.vertices:
        lines.append(
            f"v {vertex.position.x:.6f} {vertex.position.y:.6f} {vertex.position.z:.6f}"
        )
    for vertex in mesh.vertices:
        lines.append(f"vt {vertex.uv[0]:.6f} {vertex.uv[1]:.6f}")
    for vertex in mesh.vertices:
        lines.append(
            f"vn {vertex.normal.x:.6f} {vertex.normal.y:.6f} {vertex.normal.z:.6f}"
        )
    for triangle_start in range(0, len(mesh.indices), 3):
        i0, i1, i2 = (
            mesh.indices[triangle_start] + 1,
            mesh.indices[triangle_start + 1] + 1,
            mesh.indices[triangle_start + 2] + 1,
        )
        lines.append(f"f {i0}/{i0}/{i0} {i1}/{i1}/{i1} {i2}/{i2}/{i2}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def port_h1z1_actor(args: argparse.Namespace) -> dict:
    source_dir = args.source.resolve()
    adr_path = source_dir / f"{args.actor}.adr"
    if not adr_path.is_file():
        raise FileNotFoundError(f"H1Z1 actor not found: {adr_path}")

    h1_actor = H1Z1Actor.load(adr_path)
    mesh_name = _mesh_file_for_lod(h1_actor, args.lod)
    mesh_path = source_dir / mesh_name
    if not mesh_path.is_file():
        raise FileNotFoundError(f"H1Z1 mesh not found: {mesh_path}")

    dme = DmeFile.load(mesh_path)
    imported = _dme_to_imported_mesh(dme)

    preview_dir = (
        Path(__file__).resolve().parent.parent
        / "output"
        / "h1z1_port"
        / args.actor
        / "preview"
    )
    preview_dir.mkdir(parents=True, exist_ok=True)
    intermediate_obj = preview_dir / f"{args.actor}_lod{args.lod}.obj"
    _write_temp_obj(imported, intermediate_obj)

    if args.export_preview:
        export_obj(dme, preview_dir / f"{Path(mesh_name).stem}.obj")

    mesh_stem = Path(mesh_name).stem.rsplit("_LOD", 1)[0].rsplit("_Lod", 1)[0]
    texture_path = resolve_h1z1_diffuse_path(
        source_dir,
        h1_actor,
        dme.dma.textures,
        mesh_stem=mesh_stem,
    )
    diffuse_name = texture_path.name if texture_path else h1_actor.diffuse_texture()
    _, adr_template, _, dma_template, _ = _load_template_assets(
        args.template.resolve(),
        args.replace,
    )

    fr_texture_slots = _build_fr_texture_slots(dma_template.textures)

    output_dir = (
        args.output
        or Path(__file__).resolve().parent.parent
        / "output"
        / "sg_warpstone_01_loose"
        / args.actor.lower()
    ).resolve()

    convert_args = argparse.Namespace(
        input=intermediate_obj,
        replace=args.replace,
        no_replace=False,
        name=None,
        template=args.template.resolve(),
        output=output_dir,
        scale=None,
        skeleton="treeble",
        copy_animations=None,
        texture=texture_path,
        pack=args.pack,
        write_adr=None,
        mesh_scale=1.0,
        mesh_offset=(0.0, 0.0, 0.0),
        preserve_extra_meshes=not args.no_preserve_extra_meshes,
        fit_template=not args.no_fit_template,
        mesh_only=False,
    )
    manifest = convert_assets(convert_args)

    naming = ActorNaming.from_template(args.replace, adr_template, dma_template)

    copied_textures: list[str] = []

    def _copy_h1z1_texture(name: str) -> None:
        if not name:
            return
        source_texture = source_dir / name
        if not source_texture.is_file():
            return
        shutil.copy2(source_texture, output_dir / name)
        if name not in copied_textures:
            copied_textures.append(name)

    for tex_name in dme.dma.textures:
        _copy_h1z1_texture(tex_name)
    for alias in h1_actor.texture_aliases:
        _copy_h1z1_texture(alias.texture_name)
    if diffuse_name:
        _copy_h1z1_texture(diffuse_name)

    template_dir = args.template.resolve()
    fx_texture_name = dma_template.textures[1] if len(dma_template.textures) > 1 else ""
    fx_target = output_dir / fx_texture_name
    fx_source = template_dir / fx_texture_name
    if not fx_source.is_file():
        fx_source = template_dir / naming.texture_file
    if (
        fx_texture_name
        and fx_target.name.lower() != naming.texture_file.lower()
        and fx_source.is_file()
        and fx_texture_name not in copied_textures
    ):
        shutil.copy2(fx_source, fx_target)
        copied_textures.append(fx_texture_name)

    if texture_path:
        shutil.copy2(texture_path, output_dir / naming.texture_file)
        if naming.texture_file not in copied_textures:
            copied_textures.append(naming.texture_file)

    if args.pack:
        _pack_directory(output_dir)

    manifest["h1z1_source"] = str(source_dir)
    manifest["h1z1_actor"] = args.actor
    manifest["h1z1_mesh"] = mesh_name
    manifest["h1z1_diffuse"] = diffuse_name
    manifest["h1z1_dma_textures"] = fr_texture_slots
    manifest["h1z1_texture_resolved"] = bool(texture_path)
    manifest["intermediate_obj"] = str(intermediate_obj)
    manifest["imported_vertices"] = len(imported.vertices)
    manifest["imported_triangles"] = len(imported.indices) // 3
    manifest["copied_h1z1_textures"] = copied_textures
    manifest["notes"] = list(manifest.get("notes", [])) + [
        f"Ported from H1Z1 XML actor {args.actor}.adr (ForgeLight v4 DME).",
        f"Source mesh: {mesh_name} ({len(imported.vertices)} verts, {len(imported.indices)//3} tris).",
        "H1Z1 XML .adr is NOT copied - Free Realms uses binary .adr from the template.",
        (
            f"Diffuse copied to {naming.texture_file} from {diffuse_name} "
            f"(FR shader reads slot 0: {fr_texture_slots[0]})."
            if texture_path and diffuse_name
            else "WARNING: No H1Z1 color map found - template texture used."
        ),
        "Extra H1Z1 maps (_N/_S/etc.) are copied but FR warpstone shaders only sample slot 0.",
        f"Copied {len(copied_textures)} texture file(s).",
    ]
    (output_dir / "install.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    args = parse_args()
    manifest = port_h1z1_actor(args)
    print(f"Ported {manifest['h1z1_actor']} -> {manifest['actor']}")
    print(f"Output: {manifest['output_dir']}")
    print(
        f"Mesh: {manifest['imported_vertices']} verts, "
        f"{manifest['imported_triangles']} tris"
    )
    if manifest.get("h1z1_diffuse"):
        print(f"Diffuse: {manifest['h1z1_diffuse']}")
    print()
    for line in manifest.get("notes", []):
        print(f"  - {line}")


if __name__ == "__main__":
    main()
