"""Generate private guards for authored snippets in the owned fixture PE."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
import pefile

parser = argparse.ArgumentParser()
parser.add_argument("image", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
pe = pefile.PE(str(args.image))
start = next(row.address for row in pe.DIRECTORY_ENTRY_EXPORT.symbols if row.name == b"OwnedCode")
patterns = {"Xor": bytes.fromhex("8b0c8b330c82"), "NegAdd": bytes.fromhex("8b0c8bf7d9030c82"),
            "Compare": bytes.fromhex("8b04828b148b3bc2"), "InputTransform": bytes.fromhex("8b0c8b330c82")}
families = ["Xor"] * 247 + ["NegAdd"] * 259 + ["Compare"] * 847 + ["InputTransform"] * 12
def array(value):
    return "{" + ",".join(f"0x{x:02x}" for x in value) + "}"
lines = ["#pragma once", "#include \"ProfileTypes.h\"", "namespace bo3::code_integrity {",
         f"constexpr auto kExecutableDigest=std::array<unsigned char,32>{array(hashlib.sha256(args.image.read_bytes()).digest())};",
         f"constexpr std::uint32_t kTimestamp={pe.FILE_HEADER.TimeDateStamp}u,kImageSize={pe.OPTIONAL_HEADER.SizeOfImage}u;",
         f"constexpr std::array<Region,2> kRegions{{Region{{{start}u,131072u}},Region{{{start+131072}u,131072u}}}};",
         "constexpr std::array<Record,1365> kRecords{{"]
seed = []
for index, family in enumerate(families):
    rva = start + 64 + index * 128
    consumer = bytes.fromhex("330c82894d44" if family == "InputTransform" else "0f8400000000")
    transport = bytes.fromhex("49bb") + bytes(8) if index == 0 else b""
    guard = patterns[family] + transport + consumer
    flags = "ZeroCarry" if family == "Compare" else "Zero"
    fields = f"{{ImageAddress{{{len(patterns[family])+2}u,{start}u}}}}" if index == 0 else "{}"
    lines.append(f"Record{{{rva}u,Family::{family},Flags::{flags},{len(guard)}u,{array(hashlib.sha256(guard).digest())},{fields},{1 if index==0 else 0}u}},")
    seed.append({"rva":rva,"size":len(guard),"bytes":guard.hex(),"imageAddressFields":[{"offset":len(patterns[family])+2,"targetRva":start}] if index==0 else []})
lines.extend(["}};", f"constexpr std::array<Guard,1> kContextGuards{{Guard{{{start+60}u,4u,{array(hashlib.sha256(bytes([0x90])*4).digest())},{{}},0u}}}};", "}"])
args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
seed.append({"rva":start+60,"size":4,"bytes":"90909090","imageAddressFields":[]})
(args.output.parent / "fixture-seed.json").write_text(json.dumps({"scope":"authored inert snippets only; imageAddressFields must be seeded as current imageBase+targetRva", "records":seed},indent=2)+"\n")
binary = bytearray(struct.pack("<I",len(seed)))
for record in seed:
    binary.extend(struct.pack("<II",record["rva"],record["size"]))
    binary.extend(bytes.fromhex(record["bytes"]))
(args.output.parent / "fixture-seed.bin").write_bytes(binary)
(args.output.parent / "fixture-profile.json").write_text(json.dumps({"scope":"authored inert fixture", "imageSha256":hashlib.sha256(args.image.read_bytes()).hexdigest(), "startRva":start, "records":1365, "edits":1353}, indent=2)+"\n")
