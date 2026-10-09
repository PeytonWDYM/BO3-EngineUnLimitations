"""Compile the pinned public RVA/digest manifest; captured code stays private."""
import argparse
import hashlib
import json
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parent
source = root / "exact_build_profile.json"
identity = (root / "ProfileIdentity.h").read_text()
expected = re.search(r'kProfileId\[\]="([0-9a-f]{64})"', identity).group(1)
if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
    raise SystemExit("The fixed integrity profile differs.")
p = json.loads(source.read_text())
if (p["executableSha256"] != "0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0"
        or p["timestamp"] != 0x693D731E or p["imageSize"] != 0x1D74B000
        or len(p["regions"]) != 2 or len(p["sites"]) != 1365):
    raise SystemExit("Unsupported integrity build or inventory.")
def array(value):
    return "{" + ",".join(f"0x{x:02x}" for x in value) + "}"
lines = ["#pragma once", "#include \"ProfileTypes.h\"", "namespace bo3::code_integrity {",
         f"constexpr auto kExecutableDigest=std::array<unsigned char,32>{array(bytes.fromhex(p['executableSha256']))};",
         f"constexpr std::uint32_t kTimestamp={p['timestamp']}u,kImageSize={p['imageSize']}u;",
         "constexpr std::array<Region,2> kRegions{{" + ",".join(f"Region{{{r['rva']}u,{r['size']}u}}" for r in p["regions"]) + "}};",
         "constexpr std::array<Record,1365> kRecords{{"]
for site in p["sites"]:
    fields = ",".join(f"ImageAddress{{{x['offset']}u,{x['targetRva']}u}}" for x in site["imageAddresses"])
    lines.append(f"Record{{{site['rva']}u,Family::{site['family']},Flags::{site['liveFlags']},{site['guardSize']}u,{array(bytes.fromhex(site['guardSha256']))},{{{fields}}},{len(site['imageAddresses'])}u}},")
lines.extend(["}};", f"constexpr std::array<Guard,{len(p['contextGuards'])}> kContextGuards{{{{"])
for guard in p["contextGuards"]:
    fields = ",".join(f"ImageAddress{{{x['offset']}u,{x['targetRva']}u}}" for x in guard["imageAddresses"])
    lines.append(f"Guard{{{guard['rva']}u,{guard['size']}u,{array(bytes.fromhex(guard['sha256']))},{{{fields}}},{len(guard['imageAddresses'])}u}},")
lines.extend(["}};", "}"])
if args.output.exists():
    raise SystemExit("Use a new generated profile path.")
args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
