"""Build and inspect one private full-AAE weapon candidate without a game launch."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib


REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY / "source/patches/grenade_cleanup"))
sys.path.insert(0, str(REPOSITORY / "source/patches/weapon_tuning"))
from fastfile_candidate import decode, SOURCE_HASH
from weapon_tuning import apply_decoded, planned_edits


def verify(source: Path, output: Path) -> dict:
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_HASH:
        raise ValueError("Use the exact private full-AAE original.")
    output = output.resolve()
    if output == REPOSITORY or REPOSITORY in output.parents or output.exists():
        raise ValueError("Use a new private output directory.")
    decoded, blocks = decode(original)
    edits = planned_edits(decoded)
    desired = apply_decoded(decoded)
    candidate = bytearray(original)
    for block in blocks:
        start = block.decoded_start
        old = decoded[start:start + block.decoded_size]
        new = desired[start:start + block.decoded_size]
        if old == new:
            continue
        packed = zlib.compress(new, 9)
        if len(packed) > block.capacity:
            raise ValueError("The candidate exceeds a compressed block capacity.")
        begin = block.file_offset + 16
        candidate[begin:begin + block.capacity] = packed.ljust(block.capacity, b"\0")
        struct.pack_into("<i", candidate, block.file_offset, len(packed))
    checked, _ = decode(candidate)
    assert checked == desired
    actual = {i for i, (a, b) in enumerate(zip(decoded, checked)) if a != b}
    expected = {
        edit.offset + i
        for edit in edits
        for i, (a, b) in enumerate(zip(edit.expected, edit.replacement))
        if a != b
    }
    assert actual == expected
    assert len(candidate) == len(original)
    for edit in edits:
        assert checked[edit.offset:edit.offset + len(edit.replacement)] == edit.replacement
    rejected = []
    for name, invalid in (
        ("repeated_application", desired),
        ("truncated_records", decoded[:edits[0].offset]),
    ):
        try:
            apply_decoded(invalid)
        except ValueError:
            rejected.append(name)
        else:
            raise AssertionError(f"Accepted {name}.")
    corrupt = bytearray(decoded)
    corrupt[edits[0].offset] ^= 1
    try:
        apply_decoded(corrupt)
    except ValueError:
        rejected.append("changed_record")
    else:
        raise AssertionError("Accepted a changed weapon record.")
    restored = bytearray(checked)
    for edit in edits:
        restored[edit.offset:edit.offset + len(edit.expected)] = edit.expected
    assert restored == decoded
    report = {
        "sourceSha256": SOURCE_HASH,
        "candidateSha256": hashlib.sha256(candidate).hexdigest(),
        "decodedBytesChanged": len(actual),
        "weapons": [
            {"weapon": edit.weapon, "field": edit.field,
             "before": struct.unpack("<i", edit.expected)[0],
             "after": struct.unpack("<i", edit.replacement)[0]}
            for edit in edits
        ],
        "rejected": rejected,
        "unrelatedDecodedBytesPreserved": True,
        "restorationVerified": True,
        "gameplayValidated": False,
        "sprintFireImplemented": False,
    }
    output.mkdir(parents=True)
    (output / "core_mod.ff").write_bytes(candidate)
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.source, args.output), indent=2))
