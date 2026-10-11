"""Inventory a pinned companion capture and its extracted client script headers.

Literal matches are leads. Protected code and indirect ownership remain open.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from native_capture import NativeCapture, file_digest, require, EXACT_EXECUTABLE

COMPANION_MANIFEST = "952567b9f33ac0acce6345ebaaa0e2aec343c60b9f5e537c5d64a2673fe62a86"
COMPANION_IMAGE = "d71c88061bfb1dd05730e2f5ac21483a51286d336935cacb903c35b58b9296dd"
PROCESS_MANIFEST = "95943229c6a6cf6b8629e1c48c3a1f29891584c1f75d97f6e4a5d09425ce85e3"
SCRIPT_MAGIC = bytes.fromhex("804753430d0a001c")


def all_offsets(data, needle):
    offsets, offset = [], data.find(needle)
    while offset != -1:
        offsets.append(offset)
        offset = data.find(needle, offset + 1)
    return offsets


def script_header(path, root):
    data = path.read_bytes()
    require(len(data) >= 72 and data[:8] == SCRIPT_MAGIC, "An extracted client script has an unknown header.")
    code, exports, code_size, name = (struct.unpack_from("<I", data, offset)[0] for offset in (20, 32, 48, 52))
    export_count, = struct.unpack_from("<H", data, 58)
    require(72 <= code <= code + code_size <= len(data), "A client script code span is invalid.")
    require(0 <= exports <= exports + export_count * 20 <= len(data), "A client export table exceeds its script.")
    require(72 <= name < len(data), "A client script name exceeds its header.")
    name_end = data.index(b"\0", name)
    declared = data[name:name_end].decode("ascii")
    require(declared.endswith(".csc"), "An extracted client script declares another namespace.")
    entries = []
    for index in range(export_count):
        checksum, address, function, namespace, parameters, flags = struct.unpack_from("<IIIIBB", data, exports + index * 20)
        require(code <= address < code + code_size, "A client export has a code address outside its script.")
        entries.append({"address": address, "functionHash": function, "namespaceHash": namespace,
                        "parameterCount": parameters, "flags": flags, "checksum": checksum})
    return {"file": path.relative_to(root).as_posix(), "name": declared, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "codeOffset": code, "codeBytes": code_size,
            "codeSha256": hashlib.sha256(data[code:code + code_size]).hexdigest(),
            "exportCount": export_count, "exports": entries,
            "headerWidths": {"codeOffset": 32, "codeBytes": 32, "exportAddress": 32,
                             "exportCount": 16, "parameterCount": 8}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--companion", type=Path, required=True)
    parser.add_argument("--process", type=Path, required=True)
    parser.add_argument("--scripts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Keep each companion inventory immutable.")
    capture = NativeCapture(args.manifest, args.executable)
    require(file_digest(args.companion) == COMPANION_MANIFEST, "Unknown companion capture. Audit refused.")
    require(file_digest(args.process) == PROCESS_MANIFEST, "Unknown process manifest. Audit refused.")
    metadata = json.loads(args.companion.read_text())
    process = json.loads(args.process.read_text(encoding="utf-8-sig"))
    require(metadata["dump"] == capture.metadata["dump"], "The companion capture has another dump lineage.")
    require(process["sha256"].lower() == EXACT_EXECUTABLE, "The companion process has another executable.")
    main_module = next(row for row in process["modules"] if row["name"].lower() == "blackops3.exe")
    require(int(main_module["baseAddress"], 0) == capture.base
            and main_module["size"] == capture.metadata["imageSize"], "The companion process main module differs.")
    owner = next(row for row in process["modules"] if row["path"].lower() == metadata["module"].lower())
    require(int(owner["baseAddress"], 0) == int(metadata["baseAddress"], 0)
            and owner["size"] == metadata["imageSize"], "The companion process owner differs.")
    image = bytearray()
    for row in metadata["ranges"]:
        require(int(row["moduleOffset"], 0) == len(image), "The companion image contains a gap or overlap.")
        data = (args.companion.parent / row["file"]).read_bytes()
        require(len(data) == row["size"] and hashlib.sha256(data).hexdigest() == row["sha256"],
                "A companion capture range differs.")
        image.extend(data)
    require(len(image) == metadata["imageSize"] and hashlib.sha256(image).hexdigest() == COMPANION_IMAGE,
            "The complete companion image differs.")
    literals = []
    for value in (65000, 130000, 250001, 0x12DF230, 0x12D9960, 0x12D9740, 0x12ED3A0, 0x5124580, 0x5124680):
        literals.append({"kind": "rawDword", "value": value, "rvas": all_offsets(image, struct.pack("<I", value))})
    for rva in (0x12DF230, 0x12D9960, 0x12D9740, 0x12ED3A0, 0x5124580, 0x5124680):
        for base in (capture.base, 0x140000000):
            literals.append({"kind": "rawQwordMainAddress", "value": base + rva,
                             "rvas": all_offsets(image, struct.pack("<Q", base + rva))})
    paths = sorted(args.scripts.rglob("*.cscc"))
    require(len(paths) == 49, "The bounded extracted client script inventory differs.")
    scripts = [script_header(path, args.scripts) for path in paths]
    modules = [{"name": row["name"], "imageSize": row["size"], "baseAddress": row["baseAddress"],
                "capturedInThisAudit": row == main_module or row == owner} for row in process["modules"]]
    result = {"scope": "Exact same-dump companion and bounded extracted CSC inventory. Raw literal absence does not prove protected code, loaded-script completeness, or retained VM-ID ownership.",
              "mainExecutableSha256": EXACT_EXECUTABLE, "companionManifestSha256": COMPANION_MANIFEST,
              "companionImageSha256": COMPANION_IMAGE, "processManifestSha256": PROCESS_MANIFEST,
              "companionBytes": len(image), "companionRangeCount": len(metadata["ranges"]),
              "companionSections": metadata["sections"], "literalCandidates": literals,
              "scriptSource": "Same-session fastfile extraction, not a complete loaded client script set.",
              "clientScripts": scripts, "processModules": modules,
              "unclosedContracts": ["Protected companion indirect lookup and retained VM-ID consumers.",
                                    "Native imports, dynamically loaded modules, and injected callbacks.",
                                    "Full loaded client script set and bytecode operand ownership.",
                                    "Script strings, code positions, API values, and map-unload callbacks."],
              "activationAllowed": False, "passed": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": True, "companionBytes": len(image), "clientScripts": len(scripts),
                      "exports": sum(row["exportCount"] for row in scripts), "output": str(args.output)}))


if __name__ == "__main__":
    main()
