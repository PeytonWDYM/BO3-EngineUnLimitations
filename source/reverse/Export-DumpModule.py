"""Export captured module ranges without reconstructing missing memory."""

import argparse
import hashlib
import json
from pathlib import Path

import pefile
from minidump.minidumpfile import MinidumpFile


def export_module(dump_path: Path, module_name: str, output: Path) -> dict:
    repo = Path(__file__).resolve().parents[2]
    output = output.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("Game-derived exports must stay outside the repository.")
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")

    dump = MinidumpFile.parse(str(dump_path))
    modules = [
        module
        for module in dump.modules.modules
        if module.name.replace("\\", "/").rsplit("/", 1)[-1].casefold()
        == module_name.casefold()
    ]
    if len(modules) != 1:
        raise ValueError(f"Expected one {module_name} module, found {len(modules)}.")
    module = modules[0]
    memory = dump.memory_segments_64 or dump.memory_segments
    if memory is None:
        raise ValueError("The dump has no captured memory stream.")

    ranges = []
    file_size = dump_path.stat().st_size
    for segment in memory.memory_segments:
        start = max(module.baseaddress, segment.start_virtual_address)
        end = min(module.endaddress, segment.end_virtual_address)
        if start >= end:
            continue
        offset = segment.start_file_address + start - segment.start_virtual_address
        if offset < 0 or offset + end - start > file_size:
            raise ValueError("A captured module range extends beyond the dump file.")
        ranges.append((start, end, offset))
    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        if current[0] < previous[1]:
            raise ValueError("Captured module ranges overlap.")

    report = {
        "dump": str(dump_path.resolve()),
        "module": module.name,
        "baseAddress": hex(module.baseaddress),
        "imageSize": module.size,
        "timestamp": module.timestamp,
        "checksum": module.checksum,
        "memoryStream": "Memory64List" if dump.memory_segments_64 else "MemoryList",
        "capturedBytes": sum(end - start for start, end, _ in ranges),
        "ranges": [],
        "sections": [],
        "peHeaders": "unavailable",
    }
    output.mkdir(parents=True)
    with dump_path.open("rb") as source:
        for start, end, offset in ranges:
            name = f"range-{start:x}.bin"
            source.seek(offset)
            remaining = end - start
            digest = hashlib.sha256()
            with (output / name).open("wb") as destination:
                while remaining:
                    chunk = source.read(min(remaining, 8 * 1024 * 1024))
                    if not chunk:
                        raise EOFError("The dump ended during range export.")
                    destination.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
            report["ranges"].append({
                "address": hex(start),
                "moduleOffset": hex(start - module.baseaddress),
                "size": end - start,
                "file": name,
                "sha256": digest.hexdigest(),
            })

        header_range = next((item for item in ranges if item[0] == module.baseaddress), None)
        if header_range is not None:
            start, end, offset = header_range
            source.seek(offset)
            header = source.read(min(end - start, 65536))
            try:
                pe = pefile.PE(data=header, fast_load=True)
            except pefile.PEFormatError as error:
                report["peHeaders"] = f"invalid: {error}"
            else:
                report["peHeaders"] = "captured"
                report["preferredImageBase"] = hex(pe.OPTIONAL_HEADER.ImageBase)
                for section in pe.sections:
                    section_start = module.baseaddress + section.VirtualAddress
                    section_size = section.Misc_VirtualSize
                    section_end = section_start + section_size
                    captured = sum(
                        max(0, min(end, section_end) - max(start, section_start))
                        for start, end, _ in ranges
                    )
                    report["sections"].append({
                        "name": section.Name.decode(errors="replace").rstrip("\0"),
                        "address": hex(section_start),
                        "rva": hex(section.VirtualAddress),
                        "size": section_size,
                        "capturedBytes": captured,
                        "complete": captured == section_size,
                        "executable": bool(section.Characteristics & 0x20000000),
                    })
    report["completeImage"] = report["capturedBytes"] == module.size
    (output / "module.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--module", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = export_module(args.dump, args.module, args.output)
    print(json.dumps({key: report[key] for key in (
        "baseAddress", "imageSize", "capturedBytes", "peHeaders", "completeImage"
    )}, indent=2))


if __name__ == "__main__":
    main()
