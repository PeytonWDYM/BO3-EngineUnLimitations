"""Replay captured client tail gates with zero native associations and a stream sentinel.

This checks the actual instance branch and final DWORD. It does not test nonempty
native string associations or a complete game save. Requires Unicorn 2.1.4.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RSP, UC_X86_REG_RBP, UC_X86_REG_RBX
from unicorn.x86_const import UC_X86_REG_R12, UC_X86_REG_R13, UC_X86_REG_R14
from unicorn.x86_const import UC_X86_REG_RSI, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_RIP

from native_capture import NativeCapture, require, EXACT_EXECUTABLE, EXACT_MANIFEST

STACK, FILE, SHARED_ROOTS = 0x50000000, 0x52000000, 0x53000000
VALUE, SENTINEL = 0x12345678, 0xdeadbeef


def replay(capture, writing):
    machine = Uc(UC_ARCH_X86, UC_MODE_64)
    base = capture.base
    for rva, size in [(0x12d5000, 0x2000), (0x161000, 0x1000), (0x41d9000, 0x1000),
                      (0x5124000, 0x1000), (0xa1b0000, 0x1000), (0x2277000, 0x1000)]:
        machine.mem_map(base + rva, size)
        machine.mem_write(base + rva, capture.read(rva, size))
    for address, size in [(STACK, 0x10000), (FILE, 0x41000), (SHARED_ROOTS, 0x1000)]:
        machine.mem_map(address, size)
    roots = b"\xa5" * 0x1000
    machine.mem_write(SHARED_ROOTS, roots)
    machine.mem_write(base + 0xa1b0730, struct.pack("<Q", SHARED_ROOTS))
    machine.mem_write(base + 0x41d9eb4, struct.pack("<I", 0))
    machine.mem_write(base + 0x5124790, struct.pack("<I", VALUE if writing else 0))
    machine.reg_write(UC_X86_REG_RSP, STACK + 0x8000)
    machine.reg_write(UC_X86_REG_RBP, 1 if writing else STACK + 0x8100)
    machine.reg_write(UC_X86_REG_RBX, FILE)
    machine.reg_write(UC_X86_REG_R12, 0x78)
    machine.reg_write(UC_X86_REG_R13, base)
    machine.reg_write(UC_X86_REG_R14, 0 if writing else 1)
    machine.reg_write(UC_X86_REG_RSI, 0)
    calls, executed = [], []
    stream = struct.pack("<II", VALUE, SENTINEL)
    cursor = 0

    def read_final(_machine, _address, _size, _user):
        nonlocal cursor
        require(not writing and machine.reg_read(UC_X86_REG_RCX) == FILE
                and machine.reg_read(UC_X86_REG_RDX) == 4, "Unexpected native tail read.")
        require(cursor + 4 <= len(stream), "The native tail consumed the stream sentinel.")
        machine.mem_write(machine.reg_read(UC_X86_REG_R8), stream[cursor:cursor + 4])
        cursor += 4
        calls.append("read-final-dword")
        stack = machine.reg_read(UC_X86_REG_RSP)
        destination = struct.unpack("<Q", machine.mem_read(stack, 8))[0]
        machine.reg_write(UC_X86_REG_RSP, stack + 8)
        machine.reg_write(UC_X86_REG_RIP, destination)

    def record(_machine, address, _size, _user):
        executed.append(address - base)

    machine.mem_write(base + 0x22778b0, b"\xc3")
    machine.hook_add(UC_HOOK_CODE, read_final, begin=base + 0x22778b0, end=base + 0x22778b0)
    machine.hook_add(UC_HOOK_CODE, record)
    start, stop = (0x12d6390, 0x12d64a0) if writing else (0x12d54dc, 0x12d5574)
    machine.emu_start(base + start, base + stop, count=10000)
    require(machine.reg_read(UC_X86_REG_RIP) == base + stop, "The native tail did not reach its epilogue.")
    require(bytes(machine.mem_read(SHARED_ROOTS, len(roots))) == roots, "The client tail changed shared server roots.")
    require(not any(0x12d54ec <= rva < 0x12d5553 or 0x12d63a2 <= rva < 0x12d6443 for rva in executed),
            "The native client tail entered the server root loop.")
    if writing:
        length = struct.unpack("<I", machine.mem_read(FILE + 24, 4))[0]
        require(length == 4 and bytes(machine.mem_read(FILE + 56, length)) == struct.pack("<I", VALUE),
                "The native client writer emitted extra root words.")
    else:
        require(cursor == 4 and stream[cursor:] == struct.pack("<I", SENTINEL), "The tail stream boundary differs.")
        require(struct.unpack("<I", machine.mem_read(base + 0x5124790, 4))[0] == VALUE,
                "The final client root used the wrong instance storage.")
    return {"writing": writing, "nativeAssociations": 0, "finalDwordBytes": 4,
            "sharedServerRootsPreserved": True, "serverRootLoopSkipped": True,
            "sentinelUnread": not writing, "executedRvas": executed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.is_relative_to(Path(__file__).resolve().parents[3]), "Use an output folder outside Git.")
    require(not output.exists(), "Use a new output folder.")
    capture = NativeCapture(args.manifest, args.executable)
    results = [replay(capture, False), replay(capture, True)]
    output.mkdir(parents=True)
    receipt = {"sourceSha256": EXACT_EXECUTABLE, "manifestSha256": EXACT_MANIFEST,
               "harnessSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "scope": "Captured whole-state tail branches and native association calls with association count zero.",
               "cases": results, "activationAllowed": False}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Native client reader and writer skip server roots. Reader preserves the following stream sentinel.")


if __name__ == "__main__":
    main()
