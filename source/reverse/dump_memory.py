"""Read only captured bytes and bind a dump to its recorded process identity."""

from bisect import bisect_right
from datetime import datetime
from pathlib import Path
import struct

from minidump.minidumpfile import MinidumpFile


class DumpMemory:
    def __init__(self, path: Path):
        self.dump = MinidumpFile.parse(str(path))
        memory = self.dump.memory_segments_64 or self.dump.memory_segments
        if memory is None:
            raise ValueError("The dump has no captured memory stream.")
        self.ranges = sorted(memory.memory_segments, key=lambda item: item.start_virtual_address)
        self.starts = [item.start_virtual_address for item in self.ranges]
        file_size = path.stat().st_size
        for item in self.ranges:
            if item.start_file_address < 0 or item.start_file_address + item.size > file_size:
                raise ValueError("A memory range extends beyond the dump file.")
        for previous, current in zip(self.ranges, self.ranges[1:]):
            if current.start_virtual_address < previous.end_virtual_address:
                raise ValueError("Captured memory ranges overlap.")
        self.source = path.open("rb")

    def read(self, address: int, size: int) -> bytes:
        result = bytearray()
        end = address + size
        while address < end:
            index = bisect_right(self.starts, address) - 1
            if index < 0 or address >= self.ranges[index].end_virtual_address:
                raise ValueError(f"Memory at {address:#x} is not captured.")
            item = self.ranges[index]
            length = min(end, item.end_virtual_address) - address
            self.source.seek(item.start_file_address + address - item.start_virtual_address)
            chunk = self.source.read(length)
            if len(chunk) != length:
                raise ValueError("The dump ended during a memory read.")
            result.extend(chunk)
            address += length
        return bytes(result)

    def number(self, address: int, format_code: str) -> int:
        return struct.unpack("<" + format_code, self.read(address, struct.calcsize("<" + format_code)))[0]

    def close(self) -> None:
        self.source.close()


def verify_identity(memory: DumpMemory, profile: dict, identity: dict):
    if identity["sha256"].casefold() != profile["sha256"].casefold():
        raise ValueError("The capture executable hash differs from the profile.")
    misc = memory.dump.misc_info
    started = int(datetime.fromisoformat(identity["startedUtc"].replace("Z", "+00:00")).timestamp())
    if misc.ProcessId != identity["pid"] or misc.ProcessCreateTime != started:
        raise ValueError("The dump belongs to a different process instance.")
    matches = [item for item in memory.dump.modules.modules
               if Path(item.name).name.casefold() == profile["module"].casefold()]
    if len(matches) != 1:
        raise ValueError("The selected dump module is absent or ambiguous.")
    module = matches[0]
    if module.size != profile["imageSize"] or module.timestamp != profile["timestamp"]:
        raise ValueError("The dump module build differs from the profile.")
    captured = [item for item in identity["modules"] if item["name"].casefold() == profile["module"].casefold()]
    if len(captured) != 1 or int(captured[0]["baseAddress"], 16) != module.baseaddress or captured[0]["size"] != module.size:
        raise ValueError("The dump module differs from the capture identity.")
    return module
