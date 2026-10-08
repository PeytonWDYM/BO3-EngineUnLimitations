"""Merge checked VM and migration code guards for the enhanced launcher build."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--vm", type=Path, required=True)
parser.add_argument("--migration", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
vm = json.loads(args.vm.read_text(encoding="utf-8-sig"))
migration = json.loads(args.migration.read_text(encoding="utf-8-sig"))
if vm["executableSha256"] != migration["executableSha256"] or vm["imageSize"] != migration["imageSize"]:
    raise ValueError("The native inventories identify different game builds.")
guards = {}
for row in [*vm["codeGuards"], *migration["codeGuards"]]:
    key = row["rva"], row["size"]
    if key in guards and guards[key]["sha256"] != row["sha256"]:
        raise ValueError("The native inventories disagree about a code range.")
    guards[key] = row
vm["codeGuards"] = list(guards.values())
with args.output.open("x", encoding="utf-8") as stream:
    json.dump(vm, stream, indent=2)
    stream.write("\n")
