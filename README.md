# FR ADR Toolkit

A desktop GUI and CLI toolkit for converting 3D models into Free Realms game assets. Convert OBJ/GLB files into Free Realms actor definitions (`.adr`), meshes (`.dme`), and materials (`.dma`), or port H1Z1 ForgeLight assets into Free Realms.

## Features

- **Model to Free Realms converter** — OBJ / GLB / glTF 2.0 → `.dme` + `.dma` + `.adr`
- **H1Z1 asset porter** — Import weapons and props from H1Z1 `.dme` files and textures
- **Desktop GUI** — Point-and-click converter with presets for common use cases
- **Preset templates** — Built-in presets for Warpstone prop, Player body (`human_m`), and Chatdy NPC
- **Loose-file replacement** — Drop converted files straight into the Free Realms client folder to override stock assets
- **Format documentation** — Detailed reverse-engineering notes on `.adr`, `.dsk`, `.dme`, `.dma`, and `.gr2` formats
- **Skeleton tools** — Inspect and analyze `.dsk` hierarchy and bind poses
- **Texture support** — Accepts `.dds` textures, includes a `.jpg` to `.dds` converter

## Quick Start

### Download (no Python required)

1. Grab `FR_Asset_Converter.exe` from the [latest release](https://github.com/edenfps/fr-adr-toolkit/releases)
2. Double-click to launch — no install, no dependencies

### Run from source (Python)

```bash
python -m pip install -r requirements.txt
python fr_asset_gui.py
```

### CLI

Convert an OBJ model into Free Realms assets (replaces chatdy NPC):

```bash
python convert_to_fr.py --input myfox.obj --texture myfox.dds
```

Replace the warpstone prop:

```bash
python convert_to_fr.py --replace sg_warpstone_01 --template templates/sg_warpstone_01 --input model.obj
```

Port an H1Z1 weapon to Free Realms:

```bash
python port_h1z1_weapon.py --input Weapons_PumpShotgun01_3P --source "path/to/h1z1/assets"
```

Create a custom named actor (separate file set, no replacement):

```bash
python convert_to_fr.py --no-replace --name myfox --input myfox.obj
```

## Requirements

- Python 3.10+
- `numpy`
- `trimesh`
- `pygltflib`

Install with: `pip install -r requirements.txt`

## Project Structure

```
fr-adr-toolkit/
├── fr_asset_gui.py          # Desktop GUI application (Tkinter)
├── convert_to_fr.py         # CLI: OBJ/GLB → Free Realms asset converter
├── export_actor.py          # Extract baseline actor files from game assets
├── port_h1z1_weapon.py      # CLI: H1Z1 weapon porting
├── parse_assets.py          # Asset manifest reader
├── mesh_prep.py             # Mesh pre-processing utilities
├── jpg_to_dds.py            # JPEG → DDS texture converter
├── fr_formats/              # Format read/write library
│   ├── adr.py               # Actor definition (.adr)
│   ├── dme.py               # Mesh geometry (.dme, DMOD)
│   ├── dma.py               # Material definitions (.dma, DMAT)
│   ├── dsk.py               # Skeleton (.dsk, DSKE)
│   ├── import_obj.py        # OBJ importer
│   ├── import_gltf.py       # glTF/GLB importer
│   ├── writers.py           # Binary format writers
│   └── h1z1_port.py         # H1Z1-specific format handling
├── templates/               # Reference templates for actor replacement
├── models/                  # Test models
├── ASSET_FORMATS.md         # Reverse-engineered format documentation
└── Launch Asset Converter.bat  # One-click launcher
```

## Analysis Tools

| Script | Purpose |
|--------|---------|
| `inspect_dsk.py` | Inspect `.dsk` skeleton files |
| `probe_dsk_hier.py` / `probe_dsk_hier2.py` | Reverse-engineer skeleton hierarchy |
| `inspect_dme_tail.py` | Analyze `.dme` trailing metadata |
| `analyze_dme_tail.py` | Batch analyze DME tail blocks |
| `analyze_chatdy.py` | Chatdy NPC-specific analysis |
| `analyze_input.py` | Format input investigation |
| `quick_pcap_look.py` | Network packet inspection |
| `find_movement_addresses.py` | Memory analysis tool |

## Asset Formats

The `ASSET_FORMATS.md` file documents the reverse-engineered binary formats used by Free Realms (ForgeLight engine):

| Format | Extension | Description |
|--------|-----------|-------------|
| Actor Definition | `.adr` | Links skeleton, mesh, materials, animations, and sockets |
| Skeleton | `.dsk` | Bone names, hierarchy, and bind-pose matrices |
| Mesh | `.dme` | Skinned mesh geometry with embedded material blocks |
| Material | `.dma` | Texture references and shader parameter blocks |
| Animation | `.gr2` | Granny3D skeletal animation curves |

## License

AGPL-3.0
