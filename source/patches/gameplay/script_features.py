"""Compose guarded full-AAE command and stock storm-bow script edits.

The converter preserves script lengths, code offsets, imports and string fixups.
It changes no native actor capacity or network entity layout.
"""
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import struct
import zlib

from patches.grenade_cleanup.fastfile_candidate import decode


@dataclass(frozen=True)
class ScriptPlan:
    name: bytes
    size: int
    sha256: str
    edits: tuple[tuple[int, bytes, bytes], ...]


COMMANDS = ScriptPlan(
    b"scripts/zm/motherfucker.gsc\0", 212348,
    "245c7d155b6a87a088e1744887157de058f2839a492d3de50449f51be29b223d",
    (
        (0x184A0, bytes.fromhex("9724407e"), bytes.fromhex("9724c87e")),
        (0x184AA, bytes.fromhex("b5284070"), bytes.fromhex("b528c870")),
        (0x184B6, bytes.fromhex("493e4060"), bytes.fromhex("493ec860")),
        (0x184C4, bytes.fromhex("09334058"), bytes.fromhex("0933c858")),
        # Both comparison outcomes now reach the existing delay assignment.
        # The former query branch jumps before it creates a call frame.
        # Its existing string fixup at0x18654 remains in unreachable code.
        (0x1864E, bytes.fromhex("0e20e32d"), bytes.fromhex("bd362c00")),
    ),
)

STORM = ScriptPlan(
    b"scripts/zm/_zm_weap_elemental_bow_storm.gsc\0", 13660,
    "8d4742a7555dedc1fd1ccca9978133e881e1a9f94f5928aafa9587404ab2fc0a",
    ((0x1E5E, bytes.fromhex("a50f015a"), bytes.fromhex("a50f035a")),),
)


def _apply(decoded: bytearray, plan: ScriptPlan) -> dict:
    """Change one unique exact script. All guards run before mutation."""
    magic = bytes.fromhex("804753430d0a001c")
    starts = []
    cursor = 0
    while True:
        cursor = decoded.find(magic, cursor)
        if cursor < 0:
            break
        start = cursor
        cursor += len(magic)
        if start + plan.size > len(decoded):
            continue
        name_offset = struct.unpack_from("<I", decoded, start + 52)[0]
        if name_offset >= plan.size or decoded[start + name_offset:start + name_offset + len(plan.name)] != plan.name:
            continue
        if hashlib.sha256(decoded[start:start + plan.size]).hexdigest() == plan.sha256:
            starts.append(start)
    if len(starts) != 1:
        raise ValueError("The exact source script is absent or repeated.")
    start = starts[0]
    for offset, expected, replacement in plan.edits:
        if len(expected) != len(replacement) or offset + len(expected) > plan.size:
            raise ValueError("The script plan changes its size or exceeds its boundary.")
        if decoded[start + offset:start + offset + len(expected)] != expected:
            raise ValueError("The script instructions differ from the inspected source.")
    changes = []
    for offset, expected, replacement in plan.edits:
        decoded[start + offset:start + offset + len(expected)] = replacement
        changes.extend(start + offset + i for i, (a, b) in enumerate(zip(expected, replacement)) if a != b)
    return {"script": plan.name[:-1].decode(), "scriptStart": start, "scriptSize": plan.size, "beforeSha256": plan.sha256, "afterSha256": hashlib.sha256(decoded[start:start + plan.size]).hexdigest(), "changedOffsets": sorted(changes), "scriptOffsetsPreserved": True}


def apply_commands(decoded: bytearray) -> dict:
    """Prepare private research with a200 command cap and literal zero delay."""
    return _apply(decoded, COMMANDS)


def apply_spawn_delay(decoded: bytearray) -> dict:
    """Permit literal zero delay and retain the existing64 actor command cap."""
    return _apply(decoded, replace(COMMANDS, edits=(COMMANDS.edits[-1],)))


def apply_storm(decoded: bytearray) -> dict:
    """Use three bounded tornado models with the existing expiry and reuse paths."""
    return _apply(decoded, STORM)


def rebuild(source: bytes, desired: bytes | bytearray) -> bytes:
    """Repack changed blocks and require exact decode agreement."""
    decoded, blocks = decode(source)
    if len(decoded) != len(desired):
        raise ValueError("The transformed asset changes its decoded size.")
    candidate = bytearray(source)
    for block in blocks:
        begin = block.decoded_start
        end = begin + block.decoded_size
        if decoded[begin:end] == desired[begin:end]:
            continue
        packed = zlib.compress(desired[begin:end], 9)
        if len(packed) > block.capacity:
            raise ValueError("A transformed block exceeds its original capacity.")
        offset = block.file_offset + 16
        candidate[offset:offset + block.capacity] = packed + bytes(block.capacity - len(packed))
        struct.pack_into("<i", candidate, block.file_offset, len(packed))
    if decode(candidate)[0] != desired or len(candidate) != len(source):
        raise ValueError("The rebuilt fastfile differs from the planned decoded asset.")
    return bytes(candidate)


def transform_commands(source: bytes, resources: Path) -> bytes:
    """Transform an admitted original or cleanup candidate for patcher composition."""
    decoded, _ = decode(source)
    apply_commands(decoded)
    return rebuild(source, decoded)


def transform_storm(source: bytes, resources: Path) -> bytes:
    """Transform an admitted stock Der Eisendrache patch fastfile."""
    decoded, _ = decode(source)
    apply_storm(decoded)
    return rebuild(source, decoded)
