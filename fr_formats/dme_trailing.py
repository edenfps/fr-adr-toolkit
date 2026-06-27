"""Build DME trailing render-batch metadata."""



from __future__ import annotations



import struct

from functools import lru_cache

from pathlib import Path



_BALL_TEMPLATE_PATH = Path(__file__).resolve().parent / "data" / "ball_trailing_template.bin"





@lru_cache(maxsize=1)

def _ball_template() -> bytes:

    if not _BALL_TEMPLATE_PATH.exists():

        raise FileNotFoundError(

            f"Missing trailing template at {_BALL_TEMPLATE_PATH}. "

            "Regenerate from ball_m_beach.dme."

        )

    return _BALL_TEMPLATE_PATH.read_bytes()





def patch_named_batch_trailing(

    template_trailing: bytes,

    mesh_counts: list[tuple[int, int]],

) -> bytes:

    """Patch per-chunk vertex/index counts in a prop-style trailing block.



    Warpstone-style DME files use two mesh chunks (stone body + inner crystal).

    Words 7/9 hold batch-0 counts; words 16/18 hold batch-1 counts.

    """

    tail = bytearray(template_trailing)

    struct.pack_into("<I", tail, 0, len(mesh_counts))

    batch_offsets = ((7, 9), (16, 18))

    for batch_index, (vertex_count, index_count) in enumerate(mesh_counts):

        if batch_index >= len(batch_offsets):

            break

        vert_word, index_word = batch_offsets[batch_index]

        struct.pack_into("<I", tail, vert_word * 4, vertex_count)

        struct.pack_into("<I", tail, index_word * 4, index_count)

    return bytes(tail)





def build_single_batch_trailing(

    vertex_count: int,

    index_count: int,

    batch_count: int = 1,

    template_trailing: bytes | None = None,

) -> bytes:

    """Build trailing metadata for a single-batch skinned mesh."""

    if template_trailing:

        if struct.unpack_from("<I", template_trailing, 0)[0] > 1 and len(template_trailing) >= 80:

            return patch_named_batch_trailing(

                template_trailing, [(vertex_count, index_count)]

            )

        tail = bytearray(template_trailing)

        batch = struct.unpack_from("<I", template_trailing, 0)[0]

        struct.pack_into("<I", tail, 0, batch)

        struct.pack_into("<I", tail, 28, vertex_count)

        struct.pack_into("<I", tail, 36, index_count)

        return bytes(tail)



    tail = bytearray(_ball_template())

    struct.pack_into("<I", tail, 0, batch_count)

    struct.pack_into("<I", tail, 28, vertex_count)

    struct.pack_into("<I", tail, 36, index_count)

    return bytes(tail)





def _patch_scaled_trailing_counts(

    tail: bytearray,

    template_vertex_count: int,

    template_index_count: int,

    vertex_count: int,

    index_count: int,

) -> None:

    if template_vertex_count == vertex_count and template_index_count == index_count:

        return



    vert_ratio = vertex_count / template_vertex_count

    index_ratio = index_count / template_index_count



    for offset in range(0, len(tail) - 3, 4):

        value = struct.unpack_from("<I", tail, offset)[0]

        if value == template_vertex_count:

            struct.pack_into("<I", tail, offset, vertex_count)

        elif value == template_index_count:

            struct.pack_into("<I", tail, offset, index_count)

        elif value == 238:

            struct.pack_into("<I", tail, offset, max(1, int(round(238 * vert_ratio))))

        elif value == 972:

            struct.pack_into("<I", tail, offset, max(1, int(round(972 * index_ratio))))

        elif 100 < value <= template_vertex_count:

            scaled = max(1, int(round(value * vert_ratio)))

            if scaled <= vertex_count:

                struct.pack_into("<I", tail, offset, scaled)

        elif 100 < value <= template_index_count:

            scaled = max(1, int(round(value * index_ratio)))

            if scaled <= index_count:

                struct.pack_into("<I", tail, offset, scaled)





def build_multibatch_trailing(

    template_trailing: bytes,

    vertex_count: int,

    index_count: int,

    batch_count: int,

    template_vertex_count: int | None = None,

    template_index_count: int | None = None,

) -> bytes:

    """Clone and patch a multi-batch trailing block from a template mesh."""

    tail = bytearray(template_trailing)

    struct.pack_into("<I", tail, 0, batch_count)

    if template_vertex_count and template_index_count:

        _patch_scaled_trailing_counts(

            tail,

            template_vertex_count,

            template_index_count,

            vertex_count,

            index_count,

        )

    return bytes(tail)





def build_trailing(

    vertex_count: int,

    index_count: int,

    mesh_unknown: tuple[int, int, int] | None = None,

    template_trailing: bytes | None = None,

    template_vertex_count: int | None = None,

    template_index_count: int | None = None,

) -> bytes:

    batch_count = mesh_unknown[0] if mesh_unknown else 1

    if batch_count > 1:

        if not template_trailing:

            raise ValueError(

                f"Mesh declares {batch_count} render batches but no trailing template was provided."

            )

        return build_multibatch_trailing(

            template_trailing,

            vertex_count,

            index_count,

            batch_count,

            template_vertex_count,

            template_index_count,

        )

    return build_single_batch_trailing(

        vertex_count,

        index_count,

        batch_count,

        template_trailing=template_trailing,

    )





def default_mesh_unknown(batch_count: int = 1) -> tuple[int, int, int]:

    """Mesh header unknown fields paired with single-batch trailing."""

    return (batch_count, 24, -1)

