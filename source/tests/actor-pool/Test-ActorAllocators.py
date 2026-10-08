"""Replay exact captured allocator boundaries in owned memory.

Stop before native allocation initialization. This does not patch or launch BO3.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


def run(module: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RBX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_RDI, UC_X86_REG_RSP

    output = output.resolve()
    lab = (Path.home() / ".codex/labs/bo3-engine").resolve()
    if lab not in output.parents or output.exists():
        raise ValueError("Use a new result file inside the private BO3 lab.")
    meta = json.loads(module.read_text())
    base = int(meta["baseAddress"], 0)

    def read(rva: int, size: int, expected: str) -> bytes:
        for item in meta["ranges"]:
            start = int(item["moduleOffset"], 0)
            if start <= rva and rva + size <= start + item["size"]:
                raw = (module.parent / item["file"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                    raise ValueError("A captured module range differs from its manifest.")
                code = raw[rva - start:rva - start + size]
                if hashlib.sha256(code).hexdigest() != expected:
                    raise ValueError("The allocator differs from the verified capture.")
                return code
        raise ValueError("The captured allocator range is absent.")

    allocators = [
        ("actor", 0x24AB010, 0x24AB047, 0xA1B0798, 64, 0x2110, 0, UC_X86_REG_RBX,
         "078d865b2f7871198f34b79e75c4ce5098dccaf364c5b766f2ab5a7fda34c3a7"),
        ("sentient", 0x2505CF0, 0x2505D3A, 0xA1B0790, 104, 0x3088, 0xA0, UC_X86_REG_RDI,
         "d9cd241e30f9483486d67d1a3eff19f3dd5b72c943922abb20112035649ecb72"),
    ]
    results = []
    for name, start, selected, pointer, count, stride, flag, selected_register, digest in allocators:
        original = read(start, selected - start, digest)
        cases = [("empty", 0, False, 0), ("last_stock_slot", count - 1, False, count - 1),
                 ("free_expanded_slots_ignored", count, False, None)]
        if name == "actor":
            cases.append(("one_byte_200_edit_is_negative", count - 1, True, None))
        for case, occupied, mutate, expected in cases:
            code = bytearray(original)
            if mutate:
                # CMP r64, imm8 sign-extends C8 to -56, not positive 200.
                assert code[0x24AB034 - start:0x24AB038 - start] == bytes.fromhex("4883f840")
                code[0x24AB037 - start] = 200
            machine = Uc(UC_ARCH_X86, UC_MODE_64)
            machine.mem_map((base + start) & ~4095, 4096)
            machine.mem_write(base + start, bytes(code))
            machine.mem_map((base + pointer) & ~4095, 4096)
            pool_address = 0x500000
            pool = bytearray(200 * stride)
            for index in range(occupied):
                pool[index * stride + flag] = 1
            machine.mem_map(pool_address, (len(pool) + 4095) & ~4095)
            machine.mem_write(pool_address, bytes(pool))
            machine.mem_write(base + pointer, struct.pack("<Q", pool_address))
            machine.mem_map(0x300000, 0x4000)
            machine.mem_map(0x400000, 4096)
            machine.mem_write(0x302000, struct.pack("<Q", 0x400000))
            machine.reg_write(UC_X86_REG_RSP, 0x302000)
            selection = []

            def stop_at_selection(uc, address, size, user_data):
                if address == base + selected:
                    selection.append((uc.reg_read(selected_register) - pool_address) // stride)
                    uc.emu_stop()

            machine.hook_add(UC_HOOK_CODE, stop_at_selection)
            machine.emu_start(base + start, 0x400000, count=4000)
            observed = selection[0] if selection else None
            assert observed == expected, (name, case, observed, expected)
            if observed is None:
                assert machine.reg_read(UC_X86_REG_RAX) == 0
            assert bytes(machine.mem_read(pool_address, len(pool))) == bytes(pool)
            results.append({"allocator": name, "case": case, "selectedIndex": observed,
                            "poolUnchanged": True, "capturedCodeSha256": digest})
    # Execute the native table reset before any following game call or field access.
    reset_start, reset_end = 0x25063F0, 0x250647F
    reset_digest = "d3bddaa583d531e12d75db2687c921bbf25313c969e543bb0e49c67f227c6743"
    reset_code = read(reset_start, reset_end - reset_start, reset_digest)
    reset_results = []
    for index in (0, 103, 104, 199):
        machine = Uc(UC_ARCH_X86, UC_MODE_64)
        machine.mem_map((base + reset_start) & ~4095, 4096)
        machine.mem_write(base + reset_start, reset_code)
        pointer = base + 0xA1B0790
        machine.mem_map(pointer & ~4095, 4096)
        pool_address = 0x500000
        # Three records expose the invalid writes past the owner's record.
        pool = bytes([0xA5]) * (3 * 0x3088)
        machine.mem_map(pool_address, (len(pool) + 4095) & ~4095)
        machine.mem_write(pool_address, pool)
        machine.mem_write(pointer, struct.pack("<Q", pool_address))
        machine.mem_map(0x300000, 0x4000)
        machine.reg_write(UC_X86_REG_RSP, 0x302000)
        machine.reg_write(UC_X86_REG_RCX, pool_address)
        # This prefix computes an index without reading the target record.
        machine.reg_write(UC_X86_REG_RDX, pool_address + index * 0x3088)
        machine.emu_start(base + reset_start, base + reset_end, count=100)
        offset = 0x12A0 + index * 0x48
        expected = bytearray(pool)
        expected[offset:offset + 0x48] = bytes(0x48)
        assert bytes(machine.mem_read(pool_address, len(pool))) == bytes(expected)
        reset_results.append({"index": index, "firstWriteOffset": hex(offset),
                              "bytesCleared": 0x48, "overlapsTrailingFields": index == 104,
                              "outsideOwnerRecord": offset >= 0x3088})
    report = {"status": "captured_allocator_boundary_replay_passed", "cases": results,
              "tableResetCases": reset_results, "tableResetCodeSha256": reset_digest,
              "capacity200Implemented": False, "gameLaunched": False,
              "limit": "Owned pool replay stops before allocation initialization. No game stability or patch validation."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.dependencies, args.output), indent=2))
