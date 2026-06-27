#!/usr/bin/env python3
"""Generate block-letter text OBJ for Free Realms visibility testing."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import trimesh

from mesh_prep import fit_mesh_to_bounds

# 5x5 block glyphs; '.' = empty, 'x' = filled voxel.
_BLOCK_FONT: dict[str, tuple[str, ...]] = {
    "h": (
        "x...x",
        "x...x",
        "xxxxx",
        "x...x",
        "x...x",
    ),
    "e": (
        "xxxxx",
        "x....",
        "xxxx.",
        "x....",
        "xxxxx",
    ),
    "l": (
        "x....",
        "x....",
        "x....",
        "x....",
        "xxxxx",
    ),
    "o": (
        ".xxx.",
        "x...x",
        "x...x",
        "x...x",
        ".xxx.",
    ),
}

_CELL = 0.22
_DEPTH = 0.35
_LETTER_GAP = 0.18


def _glyph_boxes(char: str) -> list[trimesh.Trimesh]:
    pattern = _BLOCK_FONT.get(char.lower())
    if pattern is None:
        raise ValueError(f"No block glyph for {char!r}")

    boxes: list[trimesh.Trimesh] = []
    rows = len(pattern)
    cols = len(pattern[0])
    for row_index, row in enumerate(pattern):
        for col_index, cell in enumerate(row):
            if cell != "x":
                continue
            box = trimesh.creation.box(extents=(_CELL, _CELL, _DEPTH))
            x = col_index * _CELL + _CELL * 0.5
            y = (rows - 1 - row_index) * _CELL + _CELL * 0.5
            box.apply_translation((x, y, _DEPTH * 0.5))
            boxes.append(box)
    return boxes


def make_text(text: str) -> trimesh.Trimesh:
    """Build upright block text in the XY plane (readable from +Z)."""
    parts: list[trimesh.Trimesh] = []
    cursor_x = 0.0
    glyph_width = 5 * _CELL

    for char in text:
        if char == " ":
            cursor_x += glyph_width + _LETTER_GAP
            continue
        for box in _glyph_boxes(char):
            piece = box.copy()
            piece.apply_translation((cursor_x, 0.0, 0.0))
            parts.append(piece)
        cursor_x += glyph_width + _LETTER_GAP

    mesh = trimesh.util.concatenate(parts)
    mesh.merge_vertices()
    mesh.remove_unreferenced_vertices()
    return mesh


def _warpstone_body_bounds() -> tuple[np.ndarray, np.ndarray]:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fr_formats import DmeFile

    template = (
        Path(__file__).resolve().parent / "templates" / "sg_warpstone_01" / "sg_warpstone_01_lod0.dme"
    )
    dme = DmeFile.load(template)
    vertices = dme.meshes[0].vertices
    xs = [vertex.position.x for vertex in vertices]
    ys = [vertex.position.y for vertex in vertices]
    zs = [vertex.position.z for vertex in vertices]
    return np.array([min(xs), min(ys), min(zs)]), np.array([max(xs), max(ys), max(zs)])


def prepare_for_warpstone(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    target_min, target_max = _warpstone_body_bounds()
    return fit_mesh_to_bounds(mesh, target_min, target_max, margin=0.88)


def export_obj(mesh: trimesh.Trimesh, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(path)
    bounds = mesh.bounds
    print(f"Wrote {path} ({len(mesh.vertices)} verts, {len(mesh.faces)} faces)")
    print(
        "Bounds "
        f"x[{bounds[0][0]:.2f},{bounds[1][0]:.2f}] "
        f"y[{bounds[0][1]:.2f},{bounds[1][1]:.2f}] "
        f"z[{bounds[0][2]:.2f},{bounds[1][2]:.2f}]"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--text",
        default="hello",
        help="Text to extrude as block letters (default: hello)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "output" / "hello_test" / "source" / "hello.obj",
    )
    parser.add_argument(
        "--for-warpstone",
        action="store_true",
        help="Fit mesh to sg_warpstone_01 body bounds",
    )
    args = parser.parse_args()

    mesh = make_text(args.text)
    if args.for_warpstone:
        mesh = prepare_for_warpstone(mesh)
    export_obj(mesh, args.output)


if __name__ == "__main__":
    main()
