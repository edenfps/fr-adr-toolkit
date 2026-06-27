"""Shared mesh orientation and bounds fitting helpers."""

from __future__ import annotations

from typing import Sequence

import numpy as np
import trimesh


def mesh_bounds(mesh: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    return mesh.bounds[0].copy(), mesh.bounds[1].copy()


def fit_mesh_to_bounds(
    mesh: trimesh.Trimesh,
    target_min: Sequence[float],
    target_max: Sequence[float],
    margin: float = 0.92,
) -> trimesh.Trimesh:
    """Uniformly scale and translate mesh to sit inside target axis-aligned bounds."""
    mesh = mesh.copy()
    source_min, source_max = mesh_bounds(mesh)
    target_min = np.asarray(target_min, dtype=np.float64)
    target_max = np.asarray(target_max, dtype=np.float64)

    source_size = np.maximum(source_max - source_min, 1e-6)
    target_size = np.maximum(target_max - target_min, 1e-6)
    scale = float(np.min(target_size / source_size) * margin)

    source_center = (source_min + source_max) * 0.5
    target_center = (target_min + target_max) * 0.5
    mesh.apply_translation(-source_center)
    mesh.apply_scale(scale)
    mesh.apply_translation(target_center)
    return mesh


def orient_rat_for_vertical_prop(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Rotate a nose-along-+X rat to stand upright (+Y) facing +Z."""
    mesh = mesh.copy()
    mesh.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 0, 1]))
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    return mesh
