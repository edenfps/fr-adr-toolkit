#!/usr/bin/env python3
"""Generate a rat OBJ for Free Realms testing."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import trimesh

from mesh_prep import fit_mesh_to_bounds, orient_rat_for_vertical_prop


def make_rat() -> trimesh.Trimesh:
    """Build a clearer rat silhouette from primitives (nose points +X)."""
    parts: list[trimesh.Trimesh] = []

    abdomen = trimesh.creation.capsule(radius=0.10, height=0.22, count=(10, 10))
    abdomen.apply_translation((-0.10, 0.0, 0.08))
    parts.append(abdomen)

    torso = trimesh.creation.capsule(radius=0.13, height=0.34, count=(12, 12))
    torso.apply_translation((0.06, 0.0, 0.11))
    parts.append(torso)

    chest = trimesh.creation.icosphere(subdivisions=3, radius=0.145)
    chest.apply_scale([1.15, 0.88, 1.05])
    chest.apply_translation((0.04, 0.0, 0.12))
    parts.append(chest)

    head = trimesh.creation.icosphere(subdivisions=3, radius=0.105)
    head.apply_translation((0.30, 0.0, 0.14))
    parts.append(head)

    snout = trimesh.creation.cone(radius=0.065, height=0.15, sections=14)
    snout.apply_transform(trimesh.transformations.rotation_matrix(math.radians(90), [0, 1, 0]))
    snout.apply_translation((0.43, 0.0, 0.12))
    parts.append(snout)

    nose = trimesh.creation.icosphere(subdivisions=1, radius=0.028)
    nose.apply_translation((0.50, 0.0, 0.12))
    parts.append(nose)

    for side in (-1, 1):
        ear = trimesh.creation.icosphere(subdivisions=2, radius=0.055)
        ear.apply_scale([0.35, 1.0, 1.05])
        ear.apply_translation((0.24, 0.085 * side, 0.235))
        parts.append(ear)

    tail_segments = (
        (-0.20, 0.034, 0.11, 18),
        (-0.30, 0.028, 0.12, 24),
        (-0.40, 0.022, 0.13, 30),
        (-0.50, 0.017, 0.12, 36),
        (-0.59, 0.012, 0.10, 42),
    )
    for x_pos, radius, height, angle_deg in tail_segments:
        segment = trimesh.creation.capsule(radius=radius, height=height, count=(8, 8))
        segment.apply_transform(
            trimesh.transformations.rotation_matrix(math.radians(angle_deg), [0, 1, 0])
        )
        segment.apply_translation((x_pos, 0.0, 0.14 + radius))
        parts.append(segment)

    leg_specs = (
        (0.06, -1, 0.030, 0.11),
        (0.06, 1, 0.030, 0.11),
        (-0.08, -1, 0.026, 0.10),
        (-0.08, 1, 0.026, 0.10),
    )
    for x_pos, side, radius, length in leg_specs:
        upper = trimesh.creation.capsule(radius=radius, height=length, count=(8, 8))
        upper.apply_transform(trimesh.transformations.rotation_matrix(math.radians(75), [1, 0, 0]))
        upper.apply_translation((x_pos, 0.075 * side, 0.03))
        parts.append(upper)
        foot = trimesh.creation.icosphere(subdivisions=1, radius=radius * 1.15)
        foot.apply_scale([1.2, 0.8, 0.7])
        foot.apply_translation((x_pos, 0.11 * side, -0.015))
        parts.append(foot)

    rat = trimesh.util.concatenate(parts)
    rat.merge_vertices()
    rat.remove_unreferenced_vertices()
    rat.apply_translation((0.0, 0.0, -0.04))

    if len(rat.faces) > 1400:
        try:
            rat = rat.simplify_quadric_decimation(1200)
            rat.remove_unreferenced_vertices()
        except Exception:
            pass

    return rat


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


def prepare_for_warpstone(rat: trimesh.Trimesh) -> trimesh.Trimesh:
    rat = orient_rat_for_vertical_prop(rat)
    target_min, target_max = _warpstone_body_bounds()
    return fit_mesh_to_bounds(rat, target_min, target_max)


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
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "output" / "rat_test" / "source" / "rat.obj",
    )
    parser.add_argument(
        "--for-warpstone",
        action="store_true",
        help="Orient upright and fit to sg_warpstone_01 body bounds",
    )
    args = parser.parse_args()

    rat = make_rat()
    if args.for_warpstone:
        rat = prepare_for_warpstone(rat)
    export_obj(rat, args.output)


if __name__ == "__main__":
    main()
