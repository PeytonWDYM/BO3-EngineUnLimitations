"""Export selected x64 function boundaries from captured Windows unwind metadata."""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import struct

import pefile

from dump_memory import DumpMemory, verify_identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--rva", required=True, action="append", type=lambda value: int(value, 0))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    repo = Path(__file__).resolve().parents[2]
    if output == repo or repo in output.parents or output.exists():
        raise ValueError("Choose a new boundary file outside the repository.")
    identity = json.loads(args.identity.read_text(encoding="utf-8-sig"))
    with args.executable.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    pe = pefile.PE(str(args.executable), fast_load=True)
    if pe.FILE_HEADER.Machine != 0x8664:
        raise ValueError("This exporter requires an x64 executable.")
    profile = {"module": args.executable.name, "sha256": digest,
               "imageSize": pe.OPTIONAL_HEADER.SizeOfImage, "timestamp": pe.FILE_HEADER.TimeDateStamp}
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
    if not directory.VirtualAddress or directory.Size % 12 or directory.VirtualAddress + directory.Size > profile["imageSize"]:
        raise ValueError("The executable has no valid x64 exception directory.")
    with closing(DumpMemory(args.dump)) as memory:
        module = verify_identity(memory, profile, identity)
        rows = list(struct.iter_unpack("<III", memory.read(module.baseaddress + directory.VirtualAddress, directory.Size)))
        if any(not 0 < start < end <= module.size or not 0 <= unwind < module.size - 4 for start, end, unwind in rows):
            raise ValueError("Invalid runtime function bounds.")
        if any(first[0] >= second[0] for first, second in zip(rows, rows[1:])):
            raise ValueError("The runtime function table is not sorted.")
        roots = {}
        for row in rows:
            current = row
            visited = set()
            while True:
                if current in visited:
                    raise ValueError("The unwind chain has a cycle.")
                visited.add(current)
                start, end, unwind = current
                if not 0 < start < end <= module.size or not 0 <= unwind < module.size - 4:
                    raise ValueError("An unwind chain points outside the module.")
                header = memory.read(module.baseaddress + unwind, 4)
                version, flags = header[0] & 7, header[0] >> 3
                if version not in (1, 2):
                    raise ValueError("Unsupported unwind metadata version.")
                if not flags & 4:
                    break
                if flags & 3:
                    raise ValueError("Chained unwind metadata also defines a handler.")
                chain = unwind + 4 + ((header[2] + 1) & ~1) * 2
                if chain + 12 > module.size:
                    raise ValueError("The unwind chain extends beyond the module.")
                current = struct.unpack("<III", memory.read(module.baseaddress + chain, 12))
            roots.setdefault(current[0], []).append(row)
        functions = []
        for entry in args.rva:
            if entry not in roots:
                raise ValueError(f"No primary unwind entry at RVA {entry:#x}.")
            ranges = []
            for start, end, _ in roots[entry]:
                memory.read(module.baseaddress + start, end - start)
                ranges.append({"start": hex(module.baseaddress + start), "end": hex(module.baseaddress + end - 1)})
            functions.append({"entry": hex(module.baseaddress + entry), "ranges": ranges})
    report = {"sha256": digest, "moduleBase": hex(module.baseaddress), "functions": functions}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Exported {len(functions)} captured function boundaries: {output}")


if __name__ == "__main__":
    main()
