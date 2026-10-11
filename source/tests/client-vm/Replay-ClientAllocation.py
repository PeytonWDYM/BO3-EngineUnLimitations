"""Replay client allocation in owned emulator memory and save a repeatable receipt.

Requires Unicorn 2.1.4. Supply the exact private executable and pinned capture.
Native heap and memset calls use owned stubs. This does not test the game heap,
save codec, external references, backing lifetime, network peers, or Proton.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8
from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RSP, UC_X86_REG_RIP

from native_capture import NativeCapture, EXACT_EXECUTABLE, EXACT_MANIFEST, EXACT_NATIVE_CODE, require


POOL, HASH, STACK, DRIVER, RESULT = 0x40000000, 0x48000000, 0x50000000, 0x51000000, 0x52000000
STOP = DRIVER + 0x800


def replay(capture, allocation, initialization, instance, expected_failure):
    machine = Uc(UC_ARCH_X86, UC_MODE_64)
    base = capture.base
    for rva, size in [(0x12d9000, 0x8000), (0x3267000, 0x1000), (0x5124000, 0x1000),
                      (0x20c5000, 0x1000), (0x2bc5000, 0x1000)]:
        machine.mem_map(base + rva, size)
        machine.mem_write(base + rva, capture.read(rva, size))
    for address, size in [(STACK, 0x10000), (DRIVER, 0x1000), (RESULT, 0x200000)]:
        machine.mem_map(address, size)
    for rva, count in [(0x12df256, allocation), (0x12df419, initialization)]:
        require(struct.unpack("<I", capture.read(rva, 4))[0] == 65000, "The client immediate differs.")
        machine.mem_write(base + rva, struct.pack("<I", count))
    allocated, clears = [], []
    failure = None

    def native_return():
        stack = machine.reg_read(UC_X86_REG_RSP)
        address = struct.unpack("<Q", machine.mem_read(stack, 8))[0]
        machine.reg_write(UC_X86_REG_RSP, stack + 8)
        machine.reg_write(UC_X86_REG_RIP, address)

    def heap(_machine, _address, _size, _user):
        length = machine.reg_read(UC_X86_REG_RCX)
        target = POOL if not allocated else HASH
        require(len(allocated) < 2 and (not allocated or length == 0x40000), "Unexpected native allocation.")
        machine.mem_map(target, (length + 4095) & ~4095)
        machine.mem_write(target, b"\xa5" * length)
        allocated.append((target, length))
        machine.reg_write(UC_X86_REG_RAX, target)
        native_return()

    def clear(_machine, _address, _size, _user):
        nonlocal failure
        target = machine.reg_read(UC_X86_REG_RCX)
        length = machine.reg_read(UC_X86_REG_R8)
        if not any(start <= target and target + length <= start + size for start, size in allocated):
            failure = "clear-exceeds-allocation"
            machine.emu_stop()
            return
        require(machine.reg_read(UC_X86_REG_RDX) == 0, "Unexpected native clear value.")
        machine.mem_write(target, b"\0" * length)
        clears.append(length)
        native_return()

    machine.hook_add(UC_HOOK_CODE, heap, begin=base + 0x20c5fb0, end=base + 0x20c5fb0)
    machine.hook_add(UC_HOOK_CODE, clear, begin=base + 0x2bc53b0, end=base + 0x2bc53b0)

    def allowed(_machine, address, size, _user):
        spans = [(base + 0x12df230, base + 0x12df320), (base + 0x12df3e0, base + 0x12df4b9),
                 (base + 0x12d9960, base + 0x12d9a7b), (base + 0x20c5fb0, base + 0x20c5fb1),
                 (base + 0x2bc53b0, base + 0x2bc53b1), (DRIVER, DRIVER + 0x100)]
        require(any(start <= address and address + size <= end for start, end in spans),
                "Native execution left the audited allocation paths.")

    # Owned stub instructions make the callback boundaries independent of captured callees.
    machine.mem_write(base + 0x20c5fb0, b"\xc3")
    machine.mem_write(base + 0x2bc53b0, b"\xc3")
    machine.hook_add(UC_HOOK_CODE, allowed)

    def call(address):
        stack = STACK + 0x8008
        machine.reg_write(UC_X86_REG_RSP, stack)
        machine.mem_write(stack, struct.pack("<Q", STOP))
        machine.reg_write(UC_X86_REG_RCX, instance)
        machine.reg_write(UC_X86_REG_RDX, 0)
        machine.emu_start(address, STOP, count=100000000)

    call(base + 0x12df230)
    total = allocation if instance == 1 else 130000
    if failure is None:
        require(machine.reg_read(UC_X86_REG_RIP) == STOP, "Native initialization did not return.")
        slots = bytes(machine.mem_read(POOL, total * 64))
        for index in range(total):
            kind = struct.unpack_from("<I", slots, index * 64 + 8)[0]
            following = struct.unpack_from("<I", slots, index * 64 + 24)[0]
            if kind != (0 if index == 0 else 27) or following != (index + 1 if index + 1 < total else 0):
                failure = "incomplete-free-chain"
                break
        if failure is None:
            require(bytes(machine.mem_read(HASH, 0x40000)) == b"\0" * 0x40000, "The hash clear is incomplete.")
            roots = base + 0x512471c + instance * 0x78
            require(bytes(machine.mem_read(roots, 36)) == b"\0" * 36, "The native roots were not reset.")
            pointer = base + 0x5124500 + instance * 0x100
            require(struct.unpack("<Q", machine.mem_read(pointer, 8))[0] == HASH, "The wrong hash pointer was published.")
            require(struct.unpack("<Q", machine.mem_read(pointer + 0x80, 8))[0] == POOL, "The wrong slot pointer was published.")
    require(failure == expected_failure, "The native allocation failure differs from the expected case.")
    result = {"clientAllocationTotal": allocation, "clientInitializationTotal": initialization,
              "instance": instance, "allocatedBytes": [size for _, size in allocated], "clearedBytes": clears,
              "expectedFailure": failure}
    if failure is not None:
        return result

    # This owned caller records every DWORD ID returned by the captured object allocator.
    driver = bytearray(b"\x48\x83\xec\x28\x41\xbc" + struct.pack("<I", total - 1)
                       + b"\x49\xbd" + struct.pack("<Q", RESULT))
    loop = len(driver)
    driver += (b"\xb9" + struct.pack("<I", instance) + b"\x31\xd2\x48\xb8"
               + struct.pack("<Q", base + 0x12d9960)
               + b"\xff\xd0\x41\x89\x45\x00\x49\x83\xc5\x04\x41\xff\xcc\x75")
    driver += struct.pack("b", loop - len(driver) - 1) + b"\x48\x83\xc4\x28\xc3"
    machine.mem_write(DRIVER, bytes(driver))
    call(DRIVER)
    require(machine.reg_read(UC_X86_REG_RIP) == STOP, "Native allocation did not return.")
    ids = bytes(machine.mem_read(RESULT, (total - 1) * 4))
    require(all(value[0] == index for index, value in enumerate(struct.iter_unpack("<I", ids), 1)),
            "The native allocator lost or truncated a slot ID.")
    require(struct.unpack("<I", machine.mem_read(POOL + 24, 4))[0] == 0, "The native free list did not end.")
    reached = []

    def exhausted(_machine, address, _size, _user):
        reached.append(address)
        machine.emu_stop()

    machine.hook_add(UC_HOOK_CODE, exhausted, begin=base + 0x12d9994, end=base + 0x12d9994)
    call(base + 0x12d9960)
    require(reached == [base + 0x12d9994], "Native exhaustion did not reach the expected branch.")
    result.update({"returnedSlotCount": total - 1, "firstReturnedId": 1, "lastReturnedId": total - 1,
                   "idsSha256": hashlib.sha256(ids).hexdigest(), "nativeExhaustionBranchReached": True})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[3]
    output = args.output.resolve()
    require(not output.is_relative_to(repository), "Use an output folder outside Git.")
    require(not output.exists(), "Use a new output folder.")
    capture = NativeCapture(args.manifest, args.executable)
    output.mkdir(parents=True)
    cases = [(65000, 250001, 1, "clear-exceeds-allocation"),
             (250001, 65000, 1, "incomplete-free-chain"),
             (65000, 65000, 1, None), (250001, 250001, 1, None),
             (500001, 500001, 1, None), (500001, 500001, 0, None)]
    results = []
    for case in cases:
        started = time.monotonic()
        result = replay(capture, *case)
        result["elapsedSeconds"] = round(time.monotonic() - started, 3)
        results.append(result)
        print(json.dumps(result), flush=True)
    receipt = {"status": "Owned native replay passed. Runtime activation remains unavailable.",
               "sourceSha256": EXACT_EXECUTABLE, "manifestSha256": EXACT_MANIFEST,
               "capturedCodeSha256": EXACT_NATIVE_CODE,
               "harnessSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "captureReaderSha256": hashlib.sha256(Path(__file__).with_name("native_capture.py").read_bytes()).hexdigest(),
               "scope": "Native client allocation and initialization with owned heap and memset stubs.",
               "activationAllowed": False, "cases": results}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
