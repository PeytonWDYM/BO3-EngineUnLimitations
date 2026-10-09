"""Replay the captured stock actor counter against owned pool states.

This verifies the64-slot counter boundary. It does not increase actor capacity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


def run(module: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64
    from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RSP
    meta = json.loads(module.read_text())
    def read(rva: int, size: int) -> bytes:
        for item in meta["ranges"]:
            start = int(item["moduleOffset"], 0)
            if start <= rva and rva + size <= start + item["size"]:
                data = (module.parent / item["file"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise ValueError("A captured module range differs from its manifest.")
                return data[rva - start:rva - start + size]
        raise ValueError("The captured actor routine is absent.")
    rva = 0x24B15E0
    code = read(rva, 0x49)
    base = int(meta["baseAddress"], 0)
    pointer = base + 0xA1B0798
    scenarios = [("all64_free", set(), 64), ("all64_busy", set(range(64)), 0), ("half64_busy", set(range(32)), 32), ("free_extended_slots_do_not_raise_capacity", set(range(64)), 0)]
    rows = []
    for name, used, expected in scenarios:
        machine = Uc(UC_ARCH_X86, UC_MODE_64)
        machine.mem_map((base + rva) & ~4095, 4096)
        machine.mem_write(base + rva, code)
        machine.mem_map(pointer & ~4095, 4096)
        pool_address = 0x500000
        # Deliberately provide200 owned slots. The native counter still sees64.
        pool = bytearray(200 * 0x2110)
        for index in used:
            pool[index * 0x2110] = 1
        machine.mem_map(pool_address, (len(pool) + 4095) & ~4095)
        machine.mem_write(pool_address, bytes(pool))
        machine.mem_write(pointer, struct.pack("<Q", pool_address))
        machine.mem_map(0x300000, 4096)
        machine.mem_map(0x400000, 4096)
        machine.mem_write(0x300800, struct.pack("<Q", 0x400000))
        machine.reg_write(UC_X86_REG_RSP, 0x300800)
        machine.emu_start(base + rva, 0x400000, count=2000)
        result = machine.reg_read(UC_X86_REG_RAX)
        assert result == expected
        assert bytes(machine.mem_read(pool_address, len(pool))) == bytes(pool)
        rows.append({"case": name, "freeActors": result, "expected": expected, "poolUnchanged": True})
    report = {"status": "stock_actor64_boundary_proven_in_owned_replay", "capturedCodeSha256": hashlib.sha256(code).hexdigest(), "rva": hex(rva), "slotStride": 0x2110, "counterSlots": 64, "scenarios": rows, "capacity200Implemented": False, "gameLaunched": False}
    output = output.resolve()
    lab = (Path.home() / ".codex/labs/bo3-engine").resolve()
    if lab not in output.parents or output.exists():
        raise ValueError("Use a new result file inside the private BO3 lab.")
    output.parent.mkdir(exist_ok=True, parents=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--module", type=Path, required=True)
    p.add_argument("--dependencies", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(run(args.module, args.dependencies, args.output), indent=2))
