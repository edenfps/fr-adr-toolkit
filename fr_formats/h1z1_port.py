"""Helpers for porting multi-material H1Z1 meshes into Free Realms."""



from __future__ import annotations



from pathlib import Path



from .dma import DmaFile

from .dme import DmeFile, MeshChunk





def _material_index_for_chunk(

    chunk_index: int,

    vertex_count: int,

    chunk_count: int,

    color_textures: list[str],

    size_rank_by_index: dict[int, int],

) -> int:

    """Map an H1Z1 mesh chunk to a FR material slot (body/glass/interior order)."""

    if chunk_count <= 1:

        return 0



    lower_names = [name.lower() for name in color_textures]

    has_glass = any("glass" in name for name in lower_names)

    has_interior = any("interior" in name for name in lower_names)



    if chunk_count == 3 and has_glass and has_interior:

        rank = size_rank_by_index[chunk_index]

        if rank == 0:

            return 1  # glass

        if rank == 2:

            return 0  # body

        return 2  # interior



    if chunk_count == len(color_textures):

        return min(chunk_index, len(color_textures) - 1)



    return min(chunk_index, chunk_count - 1)





def h1z1_mesh_chunks(dme: DmeFile, color_textures: list[str] | None = None) -> list[MeshChunk]:

    """Convert H1Z1 DME chunks to output mesh chunks with FR material indices."""

    colors = color_textures or resolve_h1z1_material_color_textures(dme.dma.textures)

    chunk_count = len(dme.meshes)

    sizes = sorted(

        ((index, len(chunk.vertices)) for index, chunk in enumerate(dme.meshes)),

        key=lambda item: item[1],

    )

    size_rank_by_index = {index: rank for rank, (index, _) in enumerate(sizes)}



    return [

        MeshChunk(

            material_index=_material_index_for_chunk(

                index,

                len(chunk.vertices),

                chunk_count,

                colors,

                size_rank_by_index,

            ),

            unknown=chunk.unknown,

            vertices=list(chunk.vertices),

            indices=list(chunk.indices),

        )

        for index, chunk in enumerate(dme.meshes)

    ]





def resolve_h1z1_material_color_textures(textures: list[str]) -> list[str]:

    """Collect H1Z1 _C color maps in body → glass → interior order."""

    colors: list[str] = []

    for name in textures:

        lower = name.lower()

        if not lower.endswith(".dds"):

            continue

        if "_c.dds" not in lower and "_c_" not in lower:

            continue

        if name not in colors:

            colors.append(name)



    def sort_key(name: str) -> tuple[int, str]:

        lower = name.lower()

        if "interior" in lower:

            return (2, name)

        if "glass" in lower:

            return (1, name)

        return (0, name)



    colors.sort(key=sort_key)

    return colors





def build_fr_multi_material_dma(

    base_dma: DmaFile,

    material_count: int,

    color_textures: list[str],

) -> DmaFile:

    """Extend a replace-target DMA with extra slots/materials using FR-safe hashes."""

    if not base_dma.materials:

        raise ValueError("Replace-target DMA template has no material entries.")



    materials = list(base_dma.materials)

    while len(materials) < material_count:

        materials.append(materials[-1])



    texture_count = max(len(color_textures), material_count, len(base_dma.textures))

    textures = list(base_dma.textures)

    while len(textures) < texture_count:

        textures.append(textures[-1])



    slots = map_h1z1_colors_to_fr_dma(color_textures, DmaFile(textures=textures, materials=materials))

    return DmaFile(textures=slots, materials=materials)





def find_fr_multi_material_dma(

    assets_dir: Path,

    material_count: int,

    texture_count: int,

) -> DmaFile:

    """Legacy helper: scan assets for a multi-slot DMA (prefer build_fr_multi_material_dma)."""

    candidates: list[tuple[int, DmaFile]] = []



    def consider(path: Path) -> None:

        if not path.is_file():

            return

        dma = DmaFile.load(path)

        if len(dma.materials) < material_count or len(dma.textures) < texture_count:

            return

        size_delta = abs(len(dma.textures) - texture_count)

        candidates.append((size_delta, dma))



    if assets_dir.is_dir():

        for path in assets_dir.glob("*.dma"):

            consider(path)



    if not candidates:

        raise FileNotFoundError(

            f"No Free Realms DMA template with {material_count} material(s) and "

            f"{texture_count} texture slot(s) found in {assets_dir}"

        )



    candidates.sort(key=lambda item: item[0])

    return candidates[0][1]





def map_h1z1_colors_to_fr_dma(color_textures: list[str], fr_dma: DmaFile) -> list[str]:

    """Replace the leading FR DMA texture slots with H1Z1 color map filenames."""

    slots = list(fr_dma.textures)

    for index, color_name in enumerate(color_textures):

        if index < len(slots):

            slots[index] = color_name

    return slots

