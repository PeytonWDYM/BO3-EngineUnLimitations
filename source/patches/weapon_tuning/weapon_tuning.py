"""Apply the inspected full-AAE War Machine timer and split-count edits.

The release composer must verify the full fastfile identity before this call.
Record hashes keep this transform independent of unrelated script edits.
Sprint-fire permission requires a separate implementation.
"""

from dataclasses import dataclass
import hashlib
import struct


@dataclass(frozen=True)
class WeaponRecord:
    name: str
    header: int
    settings: int
    header_hash: str
    settings_hash: str
    split_count: int


@dataclass(frozen=True)
class WeaponEdit:
    weapon: str
    field: str
    offset: int
    expected: bytes
    replacement: bytes


WEAPONS = (
    WeaponRecord(
        "launcher_warmachinemp_zm", 0xB9C2B0, 0xB9C5DF,
        "e3f4bf818fe729c3b5258cfed3ce24f8cb0940b84d358831715d7189f6adf5c1",
        "362f74fee8ac11a3d75e6cdc600821a6741bfededa4f1a40894a380bb5cf18ce", 2,
    ),
    WeaponRecord(
        "launcher_warmachinemp_upgraded_zm", 0xB9F375, 0xB9F6B6,
        "22de932c14ee7c881fb7d62419e00b68134a5a936d1502926109a7fa1f19b4a6",
        "f5d1076fe7fbe7886b0d49a9a7d6ebb0a666ea87d88d292e8199cb2bff49dd7a", 7,
    ),
)


def planned_edits(decoded: bytes | bytearray) -> tuple[WeaponEdit, ...]:
    """Validate exact weapon records before returning the fixed-size edit plan."""
    result = []
    for weapon in WEAPONS:
        if hashlib.sha256(decoded[weapon.header:weapon.header + 768]).hexdigest() != weapon.header_hash:
            raise ValueError(f"The {weapon.name} header differs from the inspected asset.")
        if hashlib.sha256(decoded[weapon.settings:weapon.settings + 5616]).hexdigest() != weapon.settings_hash:
            raise ValueError(f"The {weapon.name} settings differ from the inspected asset.")
        name = weapon.name.encode() + b"\0"
        if decoded[weapon.header + 768:weapon.header + 768 + len(name)] != name:
            raise ValueError(f"The {weapon.name} serialized name differs.")
        # Native settings offsets exclude HydraX's 0x300-byte reconstruction header.
        for field, offset, before, after in (
            ("fireTime", 0xA1C, 500, 250),
            ("lastFireTime", 0xA20, 250, 125),
            ("splitProjectileCount", 0x1140, weapon.split_count, (weapon.split_count * 3 + 1) // 2),
        ):
            expected = struct.pack("<i", before)
            location = weapon.settings + offset
            if decoded[location:location + 4] != expected:
                raise ValueError(f"The {weapon.name} {field} baseline differs.")
            result.append(WeaponEdit(weapon.name, field, location, expected, struct.pack("<i", after)))
    return tuple(result)


def apply_decoded(decoded: bytes | bytearray) -> bytearray:
    """Return a copy with the six verified field edits and preserve every other byte."""
    edits = planned_edits(decoded)
    result = bytearray(decoded)
    for edit in edits:
        result[edit.offset:edit.offset + len(edit.expected)] = edit.replacement
    return result
