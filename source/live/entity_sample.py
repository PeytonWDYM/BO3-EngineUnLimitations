"""Reject observed changes before applying the snapshot pool checks."""

import importlib.util
from pathlib import Path
import struct
import sys

from windows_process import GLOBAL_FORMATS, LiveProcess


reverse = Path(__file__).resolve().parents[1] / "reverse"
sys.path.insert(0, str(reverse))
spec = importlib.util.spec_from_file_location("entity_snapshot", reverse / "Read-EntitySnapshot.py")
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class FrozenMemory:
    def __init__(self, process: LiveProcess, profile: dict, metadata: dict, pool: bytes):
        self.globals = {process.module.baseaddress + profile["globals"][name]:
                        struct.pack("<" + code, metadata[name]) for name, code in GLOBAL_FORMATS.items()}
        self.pool_address = metadata["pool"]
        self.pool = pool

    def read(self, address: int, size: int) -> bytes:
        if address in self.globals:
            value = self.globals[address]
        elif address == self.pool_address:
            value = self.pool
        else:
            raise ValueError("The snapshot requested uncaptured memory.")
        if len(value) != size:
            raise ValueError("The snapshot requested a different read size.")
        return value

    def number(self, address: int, format_code: str) -> int:
        return struct.unpack("<" + format_code, self.read(address, struct.calcsize("<" + format_code)))[0]


def sample(process: LiveProcess, profile: dict, attempts: int) -> tuple[dict | None, str | None, int]:
    layout = profile["layout"]
    size = layout["stride"] * layout["capacity"]
    reason = None
    for attempt in range(1, attempts + 1):
        try:
            before = process.metadata(profile)
            pool = process.read(before["pool"], size) if before["pool"] else b""
            middle = process.metadata(profile)
            if before != middle:
                raise ValueError("Pool metadata changed during the read.")
            second = process.read(before["pool"], size) if before["pool"] else b""
            after = process.metadata(profile)
            if before != after or pool != second:
                raise ValueError("Pool data or metadata changed between reads.")
            report = snapshot.inspect_pool(FrozenMemory(process, profile, before, pool), process.module, profile)
            return report, None, attempt
        except (ValueError, OSError) as error:
            reason = str(error)
            if not process.alive():
                break
    return None, reason, attempt
