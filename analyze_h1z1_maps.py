#!/usr/bin/env python3
"""Identify H1Z1 map/world files and enumerate their asset dependencies."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ASSET_RE = re.compile(
    rb"[\w][\w\-\.]{3,120}\.(?:adr|dme|dma|dds|cdt|dmv|gr2|mrn|cnk|ctg_pc|zone|tome|fxd)\b",
    re.I,
)
LOD_DME_RE = re.compile(rb"[A-Za-z][A-Za-z0-9_\-]{4,100}_LOD\d", re.I)
LOD_DMA_RE = re.compile(rb"[A-Za-z][A-Za-z0-9_\-]{4,100}_Lod\d", re.I)
CHUNK_NAME_RE = re.compile(r"^(?P<prefix>.+)_-?\d+_-?\d+_\d+\.cnk$", re.I)
TERRAIN_TEX_RE = re.compile(r"^(z1|z2|js)_", re.I)


def extract_embedded_refs(data: bytes) -> set[str]:
    refs: set[str] = set()
    for match in ASSET_RE.finditer(data):
        refs.add(match.group(0).decode("ascii", "ignore"))
    for match in LOD_DME_RE.finditer(data):
        refs.add(match.group(0).decode("ascii", "ignore") + ".dme")
    for match in LOD_DMA_RE.finditer(data):
        refs.add(match.group(0).decode("ascii", "ignore") + ".dma")
    return refs


def chunk_prefix(path: Path) -> str:
    match = CHUNK_NAME_RE.match(path.name)
    return match.group("prefix") if match else path.stem


def adr_dependencies(source_dir: Path, adr_name: str) -> dict:
    from fr_formats.dma import DmaFile
    from fr_formats.h1z1_adr import H1Z1Actor

    adr_path = source_dir / adr_name
    actor = H1Z1Actor.load(adr_path)
    deps: dict = {
        "meshes": [actor.mesh_file],
        "dma": [actor.palette_file],
        "texture_aliases": [alias.texture_name for alias in actor.texture_aliases],
        "lods": [],
        "sidecars": [],
    }
    for lod in actor.lods:
        deps["lods"].append(
            {
                "mesh": lod.mesh_file,
                "dma": lod.palette_file,
                "distance": lod.distance,
            }
        )
    text = adr_path.read_text(encoding="utf-8", errors="replace")
    for tag in ("CollisionData", "OcclusionData"):
        for match in re.finditer(rf'<{tag}[^>]*fileName="([^"]+)"', text):
            deps["sidecars"].append(match.group(1))

    dma_path = source_dir / actor.palette_file
    if dma_path.is_file():
        deps["dma_textures"] = list(DmaFile.load(dma_path).textures)
    return deps


def expand_adr_refs(source_dir: Path, adr_names: set[str]) -> dict[str, list[str]]:
    expanded: dict[str, list[str]] = {
        "meshes": [],
        "dma": [],
        "textures": [],
        "sidecars": [],
    }
    seen: dict[str, set[str]] = {key: set() for key in expanded}

    for adr_name in sorted(adr_names):
        adr_path = source_dir / adr_name
        if not adr_path.is_file():
            continue
        deps = adr_dependencies(source_dir, adr_name)
        for mesh in deps["meshes"]:
            if mesh not in seen["meshes"]:
                seen["meshes"].add(mesh)
                expanded["meshes"].append(mesh)
        for dma in deps["dma"]:
            if dma not in seen["dma"]:
                seen["dma"].add(dma)
                expanded["dma"].append(dma)
        for texture in deps.get("texture_aliases", []) + deps.get("dma_textures", []):
            if texture not in seen["textures"]:
                seen["textures"].add(texture)
                expanded["textures"].append(texture)
        for sidecar in deps["sidecars"]:
            if sidecar not in seen["sidecars"]:
                seen["sidecars"].add(sidecar)
                expanded["sidecars"].append(sidecar)
        for lod in deps["lods"]:
            mesh = lod.get("mesh")
            dma = lod.get("dma")
            if mesh and mesh not in seen["meshes"]:
                seen["meshes"].add(mesh)
                expanded["meshes"].append(mesh)
            if dma and dma not in seen["dma"]:
                seen["dma"].add(dma)
                expanded["dma"].append(dma)

    return expanded


def analyze_world(source_dir: Path, world: str, sample_chunks: int = 3) -> dict:
    zone_path = source_dir / f"{world}.zone"
    if not zone_path.is_file():
        raise FileNotFoundError(f"Missing zone file: {zone_path}")

    zone_refs = extract_embedded_refs(zone_path.read_bytes())
    chunk_files = sorted(source_dir.glob(f"{world}_*.cnk"))
    chunk_refs: set[str] = set()
    for chunk_path in chunk_files[:sample_chunks]:
        chunk_refs |= extract_embedded_refs(chunk_path.read_bytes())
        ctg_path = chunk_path.with_suffix(".ctg_pc")
        if ctg_path.is_file():
            chunk_refs |= extract_embedded_refs(ctg_path.read_bytes())

    adr_refs = {name for name in zone_refs if name.lower().endswith(".adr")}
    expanded = expand_adr_refs(source_dir, adr_refs)

    ext_counts = Counter(Path(name).suffix.lower() for name in zone_refs)
    terrain_textures = sorted(
        name for name in zone_refs if name.lower().endswith(".dds") and TERRAIN_TEX_RE.match(name)
    )

    return {
        "world": world,
        "zone_file": zone_path.name,
        "zone_bytes": zone_path.stat().st_size,
        "vnfo_file": f"{world}.vnfo" if (source_dir / f"{world}.vnfo").is_file() else None,
        "areas_xml": sorted(path.name for path in source_dir.glob(f"{world}Areas.xml")),
        "chunk_count": len(chunk_files),
        "ctg_count": len(list(source_dir.glob(f"{world}_*.ctg_pc"))),
        "embedded_ref_counts": dict(sorted(ext_counts.items())),
        "embedded_ref_total": len(zone_refs),
        "embedded_adr_count": len(adr_refs),
        "terrain_texture_count": len(terrain_textures),
        "sample_chunk_refs": len(chunk_refs),
        "expanded_dependencies": {
            **expanded,
            "counts": {key: len(values) for key, values in expanded.items()},
        },
        "examples": {
            "terrain_textures": terrain_textures[:15],
            "embedded_adrs": sorted(adr_refs)[:20],
            "embedded_dmes": sorted(name for name in zone_refs if name.lower().endswith(".dme"))[:20],
            "sample_chunk_refs": sorted(chunk_refs)[:20],
        },
    }


def discover_worlds(source_dir: Path) -> list[dict]:
    worlds: list[dict] = []
    for zone_path in sorted(source_dir.glob("*.zone")):
        world = zone_path.stem
        worlds.append(
            {
                "world": world,
                "zone_bytes": zone_path.stat().st_size,
                "vnfo": (source_dir / f"{world}.vnfo").is_file(),
                "areas_xml": [p.name for p in source_dir.glob(f"{world}Areas.xml")],
                "chunk_count": len(list(source_dir.glob(f"{world}_*.cnk"))),
            }
        )

    chunk_prefixes = Counter(chunk_prefix(path) for path in source_dir.glob("*.cnk"))
    for prefix, count in sorted(chunk_prefixes.items()):
        if not (source_dir / f"{prefix}.zone").is_file():
            worlds.append(
                {
                    "world": prefix,
                    "zone_bytes": 0,
                    "vnfo": (source_dir / f"{prefix}.vnfo").is_file(),
                    "areas_xml": [p.name for p in source_dir.glob(f"{prefix}Areas.xml")],
                    "chunk_count": count,
                    "note": "chunk files only (no .zone in extract)",
                }
            )
    return worlds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(r"C:\Users\bobya\Documents\ps2ls\h1z1 assets"),
        help="H1Z1 assets folder",
    )
    parser.add_argument(
        "--world",
        action="append",
        help="Analyze one world in depth (default: all .zone worlds)",
    )
    parser.add_argument(
        "--sample-chunks",
        type=int,
        default=5,
        help="Number of chunk files to scan for embedded refs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON report to this path",
    )
    args = parser.parse_args()
    source_dir = args.source.resolve()

    inventory = {
        "source_dir": str(source_dir),
        "area_manifests": sorted(path.name for path in source_dir.glob("*Areas.xml")),
        "worlds": discover_worlds(source_dir),
        "notes": [
            "H1Z1 open-world maps are split into .zone + grid .cnk/.ctg_pc chunk files.",
            "Z2Areas.xml exists but no Z2.zone / Z2_*.cnk in this extract (Z2 may share Z1 terrain or live elsewhere).",
            "Individual .adr files are prefabs placed into maps, not maps themselves.",
        ],
    }

    worlds = args.world or [entry["world"] for entry in inventory["worlds"] if entry.get("zone_bytes")]
    inventory["analysis"] = []
    for world in worlds:
        zone_path = source_dir / f"{world}.zone"
        if not zone_path.is_file():
            continue
        inventory["analysis"].append(analyze_world(source_dir, world, sample_chunks=args.sample_chunks))

    text = json.dumps(inventory, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
