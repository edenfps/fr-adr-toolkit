"""ADR (Actor Definition Resource) reader."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .common import read_chunk_records, read_compressed_length, read_null_terminated_string

_ANIMATION_PATTERN = re.compile(
    rb"\x01[\x00-\x7f]([\x20-\x7e]{1,64})\x00"
    rb"\x02[\x00-\x7f]([\x20-\x7e]{1,96}\.gr2)\x00"
    rb"(?:\x04\x04([\x00-\xff]{4}))?"
)


@dataclass
class AnimationSlot:
    slot_name: str
    gr2_file: str
    speed: float | None = None


@dataclass
class AdrFile:
    skeleton_file: str | None = None
    mesh_file: str | None = None
    material_file: str | None = None
    model_scale: float | None = None
    locomotion_animations: list[AnimationSlot] = field(default_factory=list)
    foley_slots: list[str] = field(default_factory=list)
    raw_sections: list[tuple[int, bytes]] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> AdrFile:
        data = Path(path).read_bytes()
        actor = cls()
        offset = 0

        while offset < len(data):
            section_type = data[offset]
            offset += 1
            size, offset = read_compressed_length(data, offset)
            chunk = data[offset : offset + size]
            offset += size
            actor.raw_sections.append((section_type, chunk))

            if section_type == 1:
                actor.skeleton_file = cls._read_single_string_block(chunk)
            elif section_type == 2:
                cls._parse_model_block(actor, chunk)
            elif section_type == 9:
                actor.locomotion_animations.extend(cls._parse_animation_bank(chunk))
            elif section_type == 10:
                actor.foley_slots.extend(cls._parse_foley_slots(chunk))

        return actor

    @staticmethod
    def _read_single_string_block(chunk: bytes) -> str:
        for record_type, payload in read_chunk_records(chunk):
            if record_type == 1:
                return read_null_terminated_string(payload, 0)[0]
        return read_null_terminated_string(chunk, 0)[0]

    @staticmethod
    def _parse_model_block(actor: AdrFile, chunk: bytes) -> None:
        for record_type, payload in read_chunk_records(chunk):
            if record_type == 1:
                actor.mesh_file = read_null_terminated_string(payload, 0)[0]
            elif record_type == 2:
                actor.material_file = read_null_terminated_string(payload, 0)[0]
            elif record_type == 4 and len(payload) == 4:
                actor.model_scale = struct.unpack(">f", payload)[0]

    @staticmethod
    def _parse_animation_bank(chunk: bytes) -> list[AnimationSlot]:
        animations: list[AnimationSlot] = []
        seen: set[tuple[str, str]] = set()
        for match in _ANIMATION_PATTERN.finditer(chunk):
            slot_name = match.group(1).decode("ascii")
            gr2_file = match.group(2).decode("ascii")
            speed_bytes = match.group(3)
            speed = (
                struct.unpack(">f", speed_bytes)[0] if speed_bytes is not None else None
            )
            key = (slot_name, gr2_file)
            if key in seen:
                continue
            seen.add(key)
            animations.append(
                AnimationSlot(slot_name=slot_name, gr2_file=gr2_file, speed=speed)
            )
        return animations

    @staticmethod
    def _parse_foley_slots(chunk: bytes) -> list[str]:
        slots: list[str] = []
        for match in re.finditer(rb"\x01[\x00-\x7f]((?:loc|emo)_[\x20-\x7e]{1,64})\x00", chunk):
            slot = match.group(1).decode("ascii")
            if slot not in slots:
                slots.append(slot)
        return slots
