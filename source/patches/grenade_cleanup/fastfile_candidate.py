"""Prepare one exact full-AAE asset candidate in the private lab.

This experiment does not install a game patch. Gameplay and friend compatibility
still require validation. Captured code and failure cases precede this candidate.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import zlib


SOURCE_SIZE = 54_146_432
SOURCE_HASH = "30532f605e8b3c9914dcd1169b23f9d46cd83949fdfe5b5e0fbe2ddf361d1d88"
SCRIPT_SIZE = 95_492
SCRIPT_HASH = "44518ec89df436e566b741cecce6cc76516a76ef9bef33dd9fcf6f35dea323a8"
SCRIPT_NAME = b"scripts/zm/_zm_weapons.gsc\0"
SCRIPT_MAGIC = bytes.fromhex("804753430d0a001c")
ARGUMENT_OFFSET = 0x1174
ORIGINAL_ARGUMENT = bytes.fromhex("85300036")
# A temporary integer push/pop preserves bytecode offsets and string fixups.
# With the player argument absent, the remaining zombify helper uses grenade self.
PADDING = bytes.fromhex("5f3d812f")


@dataclass(frozen=True)
class Block:
    file_offset: int
    packed_size: int
    decoded_start: int
    decoded_size: int
    capacity: int


def decode(data: bytes | bytearray) -> tuple[bytearray, list[Block]]:
    if data[:8] != b"TAff0000" or struct.unpack_from("<I", data, 8)[0] != 0x251:
        raise ValueError("The candidate requires fastfile version 0x251.")
    if data[13:16] != b"\1\0\0":
        raise ValueError("The candidate requires unencrypted PC zlib data.")
    decoded = bytearray()
    blocks = []
    position = 0x248
    while True:
        packed, size, capacity, location = struct.unpack_from("<4i", data, position)
        if not capacity:
            return decoded, blocks
        if location != position or min(packed, size, capacity) < 0 or packed > capacity:
            raise ValueError("A fastfile block has invalid dimensions.")
        if position + 16 + capacity > len(data):
            raise ValueError("A fastfile block extends beyond the file.")
        if not size:
            position = (position + 16 + 0x7FFFFF) & ~0x7FFFFF
            continue
        stream = zlib.decompressobj()
        payload = stream.decompress(data[position + 16:position + 16 + packed], size + 1)
        if len(payload) != size or not stream.eof or stream.unused_data or stream.unconsumed_tail:
            raise ValueError("A fastfile block has incomplete or excess decoded data.")
        blocks.append(Block(position, packed, len(decoded), size, capacity))
        decoded.extend(payload)
        position += 16 + capacity


def find_script(decoded: bytearray) -> int:
    matches = []
    cursor = 0
    while True:
        cursor = decoded.find(SCRIPT_MAGIC, cursor)
        if cursor < 0:
            break
        start = cursor
        cursor += len(SCRIPT_MAGIC)
        if start + SCRIPT_SIZE > len(decoded):
            continue
        name_offset = struct.unpack_from("<I", decoded, start + 52)[0]
        if name_offset >= SCRIPT_SIZE or decoded[start + name_offset:start + name_offset + len(SCRIPT_NAME)] != SCRIPT_NAME:
            continue
        if hashlib.sha256(decoded[start:start + SCRIPT_SIZE]).hexdigest() == SCRIPT_HASH:
            matches.append(start)
    if len(matches) != 1:
        raise ValueError("The exact inspected weapons script is absent or ambiguous.")
    return matches[0]


def change_script(script: bytearray) -> tuple[bytearray, int]:
    if script[ARGUMENT_OFFSET:ARGUMENT_OFFSET + 4] != ORIGINAL_ARGUMENT:
        raise ValueError("The grenade player argument differs from the inspected code.")
    cursor = struct.unpack_from("<I", script, 36)[0]
    count = struct.unpack_from("<H", script, 60)[0]
    imports = []
    for _ in range(count):
        function, namespace, references, parameters, flags = struct.unpack_from("<IIHBB", script, cursor)
        addresses = struct.unpack_from("<" + "I" * references, script, cursor + 12)
        if function == 0x183E3618:
            imports.append((cursor, namespace, parameters, flags, addresses))
        cursor += 12 + references * 4
    if len(imports) != 1 or imports[0][1:] != (0x82B91A51, 6, 4, (0x119A,)):
        raise ValueError("The utility import does not own the inspected grenade call.")
    count_offset = imports[0][0] + 10
    result = bytearray(script)
    result[ARGUMENT_OFFSET:ARGUMENT_OFFSET + 4] = PADDING
    result[count_offset] = 5
    return result, count_offset


def prepare(source: Path, output: Path) -> dict:
    source = source.resolve(strict=True)
    output = output.resolve()
    lab = (Path.home() / ".codex" / "labs" / "bo3-engine").resolve(strict=True)
    if lab not in output.parents or output.exists():
        raise ValueError("Use a new result directory inside the private BO3 lab.")
    if source.stat().st_size != SOURCE_SIZE:
        raise ValueError("The source size differs from the inspected full-AAE asset.")
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_HASH:
        raise ValueError("The source hash differs from the inspected full-AAE asset.")
    decoded, blocks = decode(original)
    start = find_script(decoded)
    script, count_offset = change_script(decoded[start:start + SCRIPT_SIZE])
    desired = bytearray(decoded)
    desired[start:start + SCRIPT_SIZE] = script
    candidate = bytearray(original)
    changed_blocks = []
    for block in blocks:
        old = decoded[block.decoded_start:block.decoded_start + block.decoded_size]
        new = desired[block.decoded_start:block.decoded_start + block.decoded_size]
        if old == new:
            continue
        payload = zlib.compress(new, 9)
        if len(payload) > block.capacity:
            raise ValueError("A changed compressed block exceeds its original capacity.")
        begin = block.file_offset + 16
        candidate[begin:begin + block.capacity] = payload + bytes(block.capacity - len(payload))
        struct.pack_into("<i", candidate, block.file_offset, len(payload))
        changed_blocks.append(block.file_offset)
    verified, _ = decode(candidate)
    if verified != desired or len(candidate) != len(original):
        raise ValueError("The candidate does not reproduce the exact planned asset data.")
    differences = [i for i, (a, b) in enumerate(zip(decoded, verified)) if a != b]
    expected = [start + ARGUMENT_OFFSET + i for i in range(4)] + [start + count_offset]
    if differences != sorted(expected):
        raise ValueError("The candidate changes data outside the five planned bytes.")
    report = {
        "status": "offline_candidate_only",
        "sourceSha256": SOURCE_HASH,
        "candidateSha256": hashlib.sha256(candidate).hexdigest(),
        "scriptBeforeSha256": SCRIPT_HASH,
        "scriptAfterSha256": hashlib.sha256(script).hexdigest(),
        "fileSizePreserved": len(candidate),
        "decodedBytesChanged": len(differences),
        "changedBlockOffsets": changed_blocks,
        "scriptCodeOffsetsPreserved": True,
        "stringRelocationsPreserved": True,
        "importParameterCount": 5,
        "gameplayValidated": False,
        "friendsValidated": False,
        "scope": "Private full-AAE experiment. This does not install or validate the final stock engine patch.",
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "core_mod.ff").write_bytes(candidate)
    (output / "weapons-candidate.gscc").write_bytes(script)
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
