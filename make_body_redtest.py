#!/usr/bin/env python3
"""Build a human_m body DME with the same shape but bright magenta vertex colors.

Use this to confirm loose-file override is actually picked up by the client.
If the torso turns magenta but the head stays normal, the override works.
"""

from __future__ import annotations

import argparse
import shutil
import zlib
from pathlib import Path

from fr_formats import DmeFile
from fr_formats.writers import write_dme


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).resolve().parent / "templates" / "human_m" / "human_m_body_lod0.dme",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "output" / "human_m_loose",
    )
    parser.add_argument("--pack", action="store_true")
    args = parser.parse_args()

    template_path = args.template.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dme = DmeFile.load(template_path)
    mesh = dme.meshes[0]
    dma_path = template_path.parent / "human_m.dma"
    dma_bytes = dma_path.read_bytes()

    for vertex in mesh.vertices:
        vertex.color = (255, 0, 255, 255)

    out_path = output_dir / "human_m_body_lod0.dme"
    write_dme(
        out_path,
        mesh.vertices,
        mesh.indices,
        dma_bytes,
        trailing_template=dme.trailing_bytes,
        mesh_unknown=mesh.unknown,
        template_vertex_count=len(mesh.vertices),
        template_index_count=len(mesh.indices),
        auto_trailing=False,
    )

    readme = output_dir / "REDTEST.txt"
    readme.write_text(
        "REDTEST: copy human_m_body_lod0.dme into your client folder.\n"
        "Expected result: male human torso becomes bright magenta.\n"
        "Head stays human (separate head actor).\n"
        "If you still look completely normal, the client is not loading this loose file.\n",
        encoding="utf-8",
    )

    if args.pack:
        (output_dir / "human_m_body_lod0.dme.z").write_bytes(
            zlib.compress(out_path.read_bytes())
        )

    print(f"Wrote {out_path}")
    print("Drop human_m_body_lod0.dme into the client folder. Torso should turn magenta.")


if __name__ == "__main__":
    main()
