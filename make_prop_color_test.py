#!/usr/bin/env python3
"""Recolor a prop DME to verify loose-file replacement is working in-game."""

from __future__ import annotations

import argparse
import shutil
import zlib
from pathlib import Path

from fr_formats import AdrFile, DmeFile
from fr_formats.writers import write_adr_preserve_template, write_dma, write_dme


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).resolve().parent / "templates" / "sg_warpstone_01",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "output" / "sg_warpstone_01_loose",
    )
    parser.add_argument("--color", default="255,0,255", help="RGBA bytes, e.g. 255,0,255,255")
    parser.add_argument("--pack", action="store_true")
    args = parser.parse_args()

    template_dir = args.template.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    adr_path = next(template_dir.glob("*.adr"))
    adr = AdrFile.load(adr_path)
    adr_bytes = adr_path.read_bytes()
    dme_path = template_dir / (adr.mesh_file or next(template_dir.glob("*.dme")).name)
    dma_path = template_dir / (adr.material_file or next(template_dir.glob("*.dma")).name)

    dme = DmeFile.load(dme_path)
    color = tuple(int(part) for part in args.color.split(","))
    if len(color) == 3:
        color = (*color, 255)

    for mesh in dme.meshes:
        for vertex in mesh.vertices:
            vertex.color = color  # type: ignore[assignment]

    actor = adr_path.stem
    write_dma(output_dir / dma_path.name, dme.dma.textures[0], template=dme.dma)
    dma_bytes = (output_dir / dma_path.name).read_bytes()
    write_dme(
        output_dir / dme_path.name,
        [],
        [],
        dma_bytes,
        trailing_template=dme.trailing_bytes,
        auto_trailing=False,
        meshes=dme.meshes,
    )
    shutil.copy2(template_dir / adr.skeleton_file, output_dir / adr.skeleton_file)
    texture_name = dma_path.with_suffix(".dds").name
    if (template_dir / texture_name).exists():
        shutil.copy2(template_dir / texture_name, output_dir / texture_name)
    write_adr_preserve_template(
        output_dir / adr_path.name,
        adr_bytes,
        adr.skeleton_file,
        adr.mesh_file,
        adr.material_file,
        adr.model_scale or 1.0,
    )

    readme = output_dir / "README.txt"
    readme.write_text(
        f"Full loose override for {actor} (Models.txt id 280 - Warpstone).\n\n"
        "Copy all files in this folder into your Free Realms client directory.\n\n"
        "Expected result: warpstones in the world turn bright magenta.\n"
        "If nothing changes, the client is not loading these loose files.\n",
        encoding="utf-8",
    )

    if args.pack:
        for path in output_dir.iterdir():
            if path.is_file() and path.suffix != ".z" and path.name != "README.txt":
                (output_dir / f"{path.name}.z").write_bytes(zlib.compress(path.read_bytes()))

    print(f"Wrote color test bundle to {output_dir}")


if __name__ == "__main__":
    main()
