"""Replay native client root release and reset cycles in owned backing.

Executes the captured shutdown suffix for six empty struct roots, the native
release/hash removal helpers, and complete native pool initialization. This
does not execute map unload callbacks, thread draining, strings, or a real arena.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RBX, UC_X86_REG_RBP
from unicorn.x86_const import UC_X86_REG_R12, UC_X86_REG_R13, UC_X86_REG_RCX
from unicorn.x86_const import UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_RSP, UC_X86_REG_RIP
from native_capture import NativeCapture, require, EXACT_EXECUTABLE, EXACT_MANIFEST

POOL, SERVER, HASH, STACK, STOP = 0x40000000, 0x42000000, 0x48000000, 0x50000000, 0x51000000


def replay(capture, total):
    machine = Uc(UC_ARCH_X86, UC_MODE_64)
    base = capture.base
    for rva, size in [(0x12d9000, 0x17000), (0x3267000, 0x1000), (0x5124000, 0x1000),
                      (0x2bc5000, 0x1000)]:
        machine.mem_map(base + rva, size); machine.mem_write(base + rva, capture.read(rva, size))
    for address, size in [(POOL, (total * 64 + 4095) & ~4095), (SERVER, 0x1000),
                          (HASH, 0x40000), (STACK, 0x10000), (STOP, 0x1000)]:
        machine.mem_map(address, size)
    server_bytes = b"\xa5" * 0x1000
    machine.mem_write(SERVER, server_bytes)
    machine.mem_write(base + 0x5124580, struct.pack("<Q", SERVER))
    machine.mem_write(base + 0x5124680, struct.pack("<Q", POOL))
    machine.mem_write(base + 0x5124600, struct.pack("<Q", HASH))
    require(capture.read(0x12df419, 4) == struct.pack("<I", 65000), "Native client reset count differs.")
    machine.mem_write(base + 0x12df419, struct.pack("<I", total))
    clears, released = [], []

    def clear(_machine, _address, _size, _user):
        target, value, size = (machine.reg_read(register) for register in (UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8))
        require(target == POOL and value == 0 and size == total * 64, "Native reset exceeded client backing.")
        machine.mem_write(target, b"\0" * size); clears.append(size)
        stack = machine.reg_read(UC_X86_REG_RSP)
        destination = struct.unpack("<Q", machine.mem_read(stack, 8))[0]
        machine.reg_write(UC_X86_REG_RSP, stack + 8); machine.reg_write(UC_X86_REG_RIP, destination)

    def allowed(_machine, address, size, _user):
        rva = address - base
        spans = ((0x12ed25c, 0x12ed344), (0x12db6b0, 0x12db798),
                 (0x12e0030, 0x12e03f2), (0x12dfc10, 0x12dfd04),
                 (0x12e04f0, 0x12e05d0), (0x12df3e0, 0x12df4b9),
                 (0x12d9740, 0x12d9860), (0x2bc53b0, 0x2bc53b1))
        require(any(start <= rva and rva + size <= end for start, end in spans),
                f"Native lifetime replay left the audited suffix at {rva:x}.")
        if rva == 0x12e0190:
            require(machine.reg_read(UC_X86_REG_RCX) == 1, "Native release selected server backing.")
            released.append(machine.reg_read(UC_X86_REG_RDX))

    machine.mem_write(base + 0x2bc53b0, b"\xc3")
    machine.hook_add(UC_HOOK_CODE, clear, begin=base + 0x2bc53b0, end=base + 0x2bc53b0)
    machine.hook_add(UC_HOOK_CODE, allowed)

    def initialize():
        machine.reg_write(UC_X86_REG_RSP, STACK + 0x8008)
        machine.mem_write(STACK + 0x8008, struct.pack("<Q", STOP))
        machine.reg_write(UC_X86_REG_RCX, 1)
        machine.emu_start(base + 0x12df3e0, STOP, count=10000000)
        require(machine.reg_read(UC_X86_REG_RIP) == STOP, "Native pool initialization did not return.")

    initialize()
    # The allocator must return a full DWORD VM ID while its entity metadata remains WORD-sized.
    machine.mem_write(POOL + 24, struct.pack("<I", total - 1))
    machine.reg_write(UC_X86_REG_RSP, STACK + 0x8008)
    machine.mem_write(STACK + 0x8008, struct.pack("<Q", STOP))
    for register, value in ((UC_X86_REG_RCX, 1), (UC_X86_REG_RDX, 3),
                            (UC_X86_REG_R8, 0x1234567890abcdef), (UC_X86_REG_R9, 2047)):
        machine.reg_write(register, value)
    machine.emu_start(base + 0x12d9740, STOP, count=10000)
    entity_id = machine.reg_read(UC_X86_REG_RAX)
    entity = bytes(machine.mem_read(POOL + entity_id * 64, 64))
    require(entity_id == total - 1 and struct.unpack_from("<HH", entity, 32) == (3, 2047), "Native entity ID or metadata width differs.")
    require(struct.unpack_from("<Q", entity, 24)[0] == 0x1234567890abcdef, "Native entity backing lost pointer bits.")
    cycles = []
    for cycle in range(2):
        initialize()
        ids = (total - 1, total - 2, min(129999, total - 3), min(65536, total - 4), min(65535, total - 5), min(65000, total - 6))
        require(len(set(ids)) == 6, "Owned root IDs overlap.")
        roots = (0x24, 0x28, 0x20, 0x2c, 0x34, 0x1c)
        data = bytearray(machine.mem_read(POOL, total * 64))
        free_ids = [index for index in range(1, total) if index not in ids]
        struct.pack_into("<I", data, 24, free_ids[0])
        for index, following in zip(free_ids, free_ids[1:] + [0]):
            struct.pack_into("<I", data, index * 64 + 24, following)
        for root, slot_id in zip(roots, ids):
            data[slot_id * 64:slot_id * 64 + 64] = b"\0" * 64
            struct.pack_into("<I", data, slot_id * 64 + 8, 22)
            struct.pack_into("<I", data, slot_id * 64 + 16, 0x101)
            machine.mem_write(base + 0x5124700 + 0x78 + root, struct.pack("<I", slot_id))
        machine.mem_write(POOL, bytes(data))
        machine.reg_write(UC_X86_REG_RSP, STACK + 0x8000)
        for register, value in ((UC_X86_REG_RBX, 1), (UC_X86_REG_RBP, 0x78),
                                (UC_X86_REG_R12, base), (UC_X86_REG_R13, 0)):
            machine.reg_write(register, value)
        machine.emu_start(base + 0x12ed25c, base + 0x12ed341, count=100000)
        require(machine.reg_read(UC_X86_REG_RIP) == base + 0x12ed341, "Native root cleanup did not reach its gate.")
        for root, slot_id in zip(roots, ids):
            require(machine.mem_read(base + 0x5124700 + 0x78 + root, 4) == b"\0" * 4, "Native shutdown retained a client root.")
            require(struct.unpack("<I", machine.mem_read(POOL + slot_id * 64 + 8, 4))[0] == 27, "Native shutdown retained a high-ID struct.")
        seen, cursor = set(), struct.unpack("<I", machine.mem_read(POOL + 24, 4))[0]
        data = bytes(machine.mem_read(POOL, total * 64))
        while cursor:
            require(0 < cursor < total and cursor not in seen, "Shutdown free chain is cyclic or truncated.")
            seen.add(cursor)
            require(struct.unpack_from("<I", data, cursor * 64 + 8)[0] == 27, "Shutdown chain contains an occupied slot.")
            cursor = struct.unpack_from("<I", data, cursor * 64 + 24)[0]
        require(len(seen) == total - 1, "Shutdown lost a free slot.")
        require(machine.mem_read(SERVER, 0x1000) == server_bytes, "Client lifecycle changed server backing.")
        require(struct.unpack("<Q", machine.mem_read(base + 0x5124680, 8))[0] == POOL, "Shutdown changed backing ownership.")
        cycles.append({"cycle": cycle, "rootIds": list(ids), "freedSlots": len(seen), "poolPointerRetained": True})
    return {"total": total, "entityReturnedId": entity_id, "entityClassWord": 3, "entityNumberWord": 2047,
            "cycles": cycles, "clearedBytes": clears, "nativeReleasedIds": released,
            "serverBackingPreserved": True, "scope": __doc__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.is_relative_to(Path(__file__).resolve().parents[3]), "Keep evidence outside Git.")
    require(not output.exists(), "Use a new output folder.")
    capture = NativeCapture(args.manifest, args.executable)
    receipt = {"executableSha256": EXACT_EXECUTABLE, "manifestSha256": EXACT_MANIFEST,
               "harnessSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "cases": [replay(capture, total) for total in (65000, 250001)], "activationAllowed": False}
    output.mkdir(parents=True)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Native client root release and reset cycles passed at stock and 250K capacities.")


if __name__ == "__main__":
    main()
