"""Parse H1Z1 / modern ForgeLight XML ActorRuntime .adr files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class H1Z1TextureAlias:
    alias_name: str
    texture_name: str
    material_index: int


@dataclass
class H1Z1Lod:
    mesh_file: str
    palette_file: str | None
    distance: float | None


@dataclass
class H1Z1Actor:
    mesh_file: str
    palette_file: str
    texture_aliases: list[H1Z1TextureAlias] = field(default_factory=list)
    lods: list[H1Z1Lod] = field(default_factory=list)
    model_scale: float = 1.0

    @classmethod
    def load(cls, path: str | Path) -> H1Z1Actor:
        root = ET.fromstring(Path(path).read_text(encoding="utf-8", errors="replace"))
        if root.tag != "ActorRuntime":
            raise ValueError(f"Expected ActorRuntime XML in {path}")

        base = root.find("Base")
        if base is None:
            raise ValueError(f"ActorRuntime missing <Base> in {path}")

        mesh_file = base.attrib.get("fileName", "")
        palette_file = base.attrib.get("paletteName", "")
        if not mesh_file or not palette_file:
            raise ValueError(f"ActorRuntime <Base> missing fileName or paletteName in {path}")

        actor = cls(mesh_file=mesh_file, palette_file=palette_file)

        for alias in root.findall("./TextureAliases/Alias"):
            actor.texture_aliases.append(
                H1Z1TextureAlias(
                    alias_name=alias.attrib.get("aliasName", ""),
                    texture_name=alias.attrib.get("textureName", ""),
                    material_index=int(alias.attrib.get("materialIndex", "0")),
                )
            )

        for lod in root.findall("./Lods/Lod"):
            lod_mesh = lod.attrib.get("fileName")
            if not lod_mesh:
                continue
            distance_text = lod.attrib.get("distance")
            actor.lods.append(
                H1Z1Lod(
                    mesh_file=lod_mesh,
                    palette_file=lod.attrib.get("paletteName"),
                    distance=float(distance_text) if distance_text else None,
                )
            )

        return actor

    def diffuse_texture(self) -> str | None:
        for alias in self.texture_aliases:
            lower = alias.texture_name.lower()
            if lower.endswith("_c.dds") or lower.endswith("_c_3p.dds"):
                return alias.texture_name
        for alias in self.texture_aliases:
            if alias.texture_name.lower().endswith(".dds"):
                return alias.texture_name
        return None


_SKIP_TEXTURE_NAMES = frozenset(
    {
        "grey.dds",
        "detail_cube.dds",
        "detail.dds",
        "black.dds",
        "white.dds",
        "default.dds",
        "defaultwhite.dds",
        "noise.dds",
    }
)


def _is_non_color_texture(name: str) -> bool:
    lower = name.lower()
    if lower in _SKIP_TEXTURE_NAMES:
        return True
    for token in (
        "_n.dds",
        "_n_",
        "_normal",
        "_s.dds",
        "_s_",
        "_spec",
        "_specular",
        "_m.dds",
        "_metal",
        "_ao.dds",
        "_oc.dds",
        "_emissive",
        "_e.dds",
        "_e_",
    ):
        if token in lower:
            return True
    if lower.endswith("_oc.dds"):
        return True
    return False


def _color_texture_score(name: str) -> tuple[int, int]:
    lower = name.lower()
    if "_c_3p" in lower or lower.endswith("_c_3p.dds"):
        return (0, len(name))
    if lower.endswith("_c.dds") or "_c.dds" in lower:
        return (1, len(name))
    if any(token in lower for token in ("_df", "_albedo", "_color", "_d.dds")):
        return (2, len(name))
    return (3, len(name))


def resolve_h1z1_diffuse_path(
    source_dir: Path,
    actor: H1Z1Actor,
    dma_textures: list[str] | None = None,
    mesh_stem: str | None = None,
) -> Path | None:
    """Find the H1Z1 color/albedo map on disk (aliases, DMA list, then glob)."""
    candidates: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if not name or name in seen or _is_non_color_texture(name):
            return
        seen.add(name)
        candidates.append(name)

    for alias in actor.texture_aliases:
        add(alias.texture_name)
    for name in dma_textures or []:
        add(name)

    candidates.sort(key=_color_texture_score)
    for name in candidates:
        path = source_dir / name
        if path.is_file():
            return path

    mesh_stem = mesh_stem or actor.mesh_file.rsplit("_LOD", 1)[0].rsplit("_Lod", 1)[0]
    actor_stem = actor.mesh_file.replace("_LOD0.dme", "").replace("_Lod0.dme", "")
    patterns = [
        f"{mesh_stem}*C*.dds",
        f"{mesh_stem}*DF*.dds",
        f"{mesh_stem}*Color*.dds",
    ]
    if actor_stem != mesh_stem:
        patterns.extend(
            [
                f"{actor_stem}*C*.dds",
                f"{actor_stem}*DF*.dds",
            ]
        )

    for pattern in patterns:
        for path in sorted(source_dir.glob(pattern)):
            if not _is_non_color_texture(path.name):
                return path
    return None
