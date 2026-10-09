"""Generate typed exact-build metadata. This does not activate or deploy a game patch."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--inventory", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
assert inventory["executableSha256"] == "0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0"
assert len(inventory["serverCountInstructions"]) == 19

def byte_list(data):
    return "{" + ",".join(f"0x{value:02x}" for value in data) + "}"

lines = ["#pragma once", '#include "GameProfile.h"', "namespace bo3::enhanced {",
         "inline constexpr std::array<CountInstruction,19> GameCounts{{"]
for row in inventory["serverCountInstructions"]:
    data = bytes.fromhex(row["bytes"])
    offset = row["immediateOffset"]
    assert 5 <= len(data) <= 6 and int.from_bytes(data[offset:offset+4], "little") == 130000
    lines.append(f"{{0x{row['rva']:x},{byte_list(data)},{len(data)},{offset}}},")
lines += ["}};", f"inline constexpr std::array<CodeGuard,{len(inventory['codeGuards'])}> GameGuards{{{{"]
for row in inventory["codeGuards"]:
    lines.append(f"{{0x{row['rva']:x},{row['size']},{byte_list(bytes.fromhex(row['sha256']))}}},")
lines += ["}};", "inline constexpr GameManifest ExactGameManifest{"]
lines.append(f"{inventory['imageSize']},{inventory['timestamp']},0x{inventory['allocationEntryRva']:x},"
             f"0x{inventory['poolPointerRva']:x},0x{inventory['hashPointerRva']:x},")
lines.append(byte_list(bytes.fromhex(inventory["allocationEntryPrefix"])) + ",")
lines.append("{{")
for row in inventory["nativeHooks"]:
    lines.append(f"{{0x{row['rva']:x},{byte_list(bytes.fromhex(row['original5']))}}},")
lines += ["}},GameCounts,GameGuards};", "}"]
assert not args.output.exists(), "Use a new generated header path."
args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
