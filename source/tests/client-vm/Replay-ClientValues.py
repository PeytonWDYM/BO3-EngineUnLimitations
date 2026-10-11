"""Replay all native value dispatches and packed stacks in owned memory.

String interning, code-position resolution, API lookup, and heap calls use owned
stubs. Native vector allocation layout and vector release logic execute. This
does not prove real arena, module, string-table, or game lifecycle ownership.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX
from unicorn.x86_const import UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_RSP, UC_X86_REG_RIP, UC_X86_REG_XMM1
from native_capture import NativeCapture, require, EXACT_EXECUTABLE, EXACT_MANIFEST

STACK, FILE, VALUES, HEAP, STOP = 0x50000000, 0x52000000, 0x53000000, 0x54000000, 0x55000000
STRING, VECTOR, PACKED, API = VALUES + 0x100, VALUES + 0x200, VALUES + 0x300, 0x1234567887654321
REGISTERS = (UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9)


class OwnedValues:
    def __init__(self, capture):
        self.capture, self.base = capture, capture.base
        self.machine = Uc(UC_ARCH_X86, UC_MODE_64)
        for rva, size in [(0x12c8000, 0x1000), (0x12d5000, 0x6000), (0x12e0000, 0x1000),
                          (0xd2000, 0x1000), (0x2277000, 0x1000), (0x2bc3000, 0x1000),
                          (0xcbc000, 0x1000), (0xcea000, 0x1000), (0x35ee000, 0x1000)]:
            self.machine.mem_map(self.base + rva, size)
            self.machine.mem_write(self.base + rva, capture.read(rva, size))
        for address, size in [(STACK, 0x10000), (FILE, 0x41000), (VALUES, 0x20000),
                              (HEAP, 0x40000), (STOP, 0x1000)]:
            self.machine.mem_map(address, size)
        self.machine.mem_write(STRING, b"owned_client_value\0")
        self.machine.mem_write(VECTOR, struct.pack("<3f", 1.5, -2.25, 4096.0))
        self.stream, self.cursor, self.heap_cursor = b"", 0, 0
        self.allocations, self.frees, self.read_sizes, self.calls = [], [], [], []
        self.code_pointer = 0x1234567890abcdef
        self.string_id = 65000
        endpoints = (0x22778b0, 0x2277750, 0x2277a60, 0xd27c0, 0xd2870, 0xd2700,
                     0xd26a0, 0xd2600, 0xd25c0, 0x12d7180, 0x12d7b40, 0x12c8a90,
                     0x12c8cf0, 0x2bc3aa0, 0x12d6b70, 0x12d5b00, 0xcbcbd0,
                     0xcbc9e0, 0xcea300)
        self.endpoints = set(endpoints)
        for rva in endpoints:
            self.machine.mem_write(self.base + rva, b"\xc3")
            self.machine.hook_add(UC_HOOK_CODE, self.stub, begin=self.base + rva, end=self.base + rva)
        self.machine.hook_add(UC_HOOK_CODE, self.allowed)

    def allowed(self, _machine, address, size, _user):
        rva = address - self.base
        spans = ((0x12d5bc0, 0x12d5eaa), (0x12d6da0, 0x12d70dc),
                 (0x12d9bb0, 0x12d9be6), (0x12e0030, 0x12e018d))
        require(rva in self.endpoints or any(start <= rva and rva + size <= end for start, end in spans),
                f"Native value execution left audited code at {rva:x}.")

    def append(self, data):
        length = struct.unpack("<I", self.machine.mem_read(FILE + 24, 4))[0]
        require(length + len(data) < 0x3fff8, "Owned value stream exceeds its buffer.")
        self.machine.mem_write(FILE + 56 + length, data)
        self.machine.mem_write(FILE + 24, struct.pack("<I", length + len(data)))

    def consume(self, count):
        require(self.cursor + count <= len(self.stream), "Native value reader exceeded the owned stream.")
        value = self.stream[self.cursor:self.cursor + count]
        self.cursor += count
        return value

    def stub(self, _machine, address, _size, _user):
        m = self.machine
        rva = address - self.base
        a, b, c, d = (m.reg_read(register) for register in REGISTERS)
        self.calls.append(rva)
        if rva == 0x22778b0:
            require(a == FILE, "Wrong read handle.")
            self.read_sizes.append(b)
            m.mem_write(c, self.consume(b))
        elif rva == 0x2277750:
            end = self.stream.find(b"\0", self.cursor)
            require(end >= self.cursor, "Owned native string lacks its terminator.")
            m.mem_write(STRING, self.consume(end - self.cursor + 1))
            m.reg_write(UC_X86_REG_RAX, STRING)
        elif rva in (0xd27c0, 0xd2870, 0xd2700, 0xd25c0):
            self.append(struct.pack("<Q", b)[:{0xd27c0: 8, 0xd2870: 4, 0xd2700: 4, 0xd25c0: 1}[rva]])
        elif rva == 0xd26a0:
            self.append(struct.pack("<I", m.reg_read(UC_X86_REG_XMM1) & 0xffffffff))
        elif rva == 0xd2600:
            data = bytes(m.mem_read(b, 128)); end = data.index(0)
            self.append(data[:end + 1])
        elif rva == 0x2277a60:
            raise ValueError("Unexpected native flush for this bounded fixture.")
        elif rva == 0x12d7180:
            require(a == self.string_id, "Native writer changed the string ID.")
            m.reg_write(UC_X86_REG_RAX, STRING)
        elif rva == 0x12d7b40:
            require(a == STRING and c == 0x18, "Native string import flags differ.")
            m.reg_write(UC_X86_REG_RAX, self.string_id)
        elif rva == 0x12c8a90:
            target = HEAP + self.heap_cursor
            self.heap_cursor += (a + 15) & ~15
            require(self.heap_cursor <= 0x40000, "Owned heap exceeded its capacity.")
            self.allocations.append({"address": target, "bytes": a, "alignmentArgument": b})
            m.mem_write(target, b"\xa5" * a)
            m.reg_write(UC_X86_REG_RAX, target)
        elif rva == 0x12c8cf0:
            self.frees.append({"address": a, "bytes": b})
        elif rva == 0x12d6b70:
            self.append(struct.pack("<Q", c))
        elif rva == 0x12d5b00:
            m.reg_write(UC_X86_REG_RAX, struct.unpack("<Q", self.consume(8))[0])
        elif rva == 0xcbcbd0:
            require(a == API, "Wrong client API pointer.")
            m.mem_write(b, struct.pack("<I", 250000)); m.mem_write(c, b"\x01")
            m.reg_write(UC_X86_REG_RAX, 1)
        elif rva in (0xcbc9e0, 0xcea300):
            require(a == 250000, "Client API index lost width.")
            m.reg_write(UC_X86_REG_RAX, API)
        elif rva != 0x2bc3aa0:
            raise ValueError(f"Unknown owned stub {rva:x}.")
        stack = m.reg_read(UC_X86_REG_RSP)
        target = struct.unpack("<Q", m.mem_read(stack, 8))[0]
        m.reg_write(UC_X86_REG_RSP, stack + 8); m.reg_write(UC_X86_REG_RIP, target)

    def call(self, rva, *arguments):
        m = self.machine
        m.reg_write(UC_X86_REG_RSP, STACK + 0x8008)
        m.mem_write(STACK + 0x8008, struct.pack("<Q", STOP))
        for register, value in zip(REGISTERS, arguments):
            m.reg_write(register, value)
        m.emu_start(self.base + rva, STOP, count=10000000)
        require(m.reg_read(UC_X86_REG_RIP) == STOP, "The native value codec did not return.")
        return m.reg_read(UC_X86_REG_RAX)

    def begin_stream(self):
        self.machine.mem_write(FILE + 24, b"\0" * 4)
        self.read_sizes.clear()

    def capture_stream(self):
        size = struct.unpack("<I", self.machine.mem_read(FILE + 24, 4))[0]
        self.stream = bytes(self.machine.mem_read(FILE + 56, size)) + struct.pack("<I", 0xdeadbeef)
        self.cursor = 0
        return size


def value_cases(capture):
    fixture = OwnedValues(capture)
    cases = []
    for numeric_type in range(28):
        value = (250000 | (129999 << 32)) if 17 <= numeric_type <= 26 else 250000
        if numeric_type in (2, 3): value = fixture.string_id
        if numeric_type == 4: value = VECTOR
        if numeric_type == 6: value = struct.unpack("<I", struct.pack("<f", -17.5))[0]
        if numeric_type in (8, 9, 16): value = 0x1234567890abcdef
        if numeric_type in (11, 12, 14): value = fixture.code_pointer
        if numeric_type == 13: value = API
        if numeric_type == 15:
            fixture.machine.mem_write(PACKED, struct.pack("<QIHHI", fixture.code_pointer, 99, 0, 20, 250000))
            value = PACKED
        fixture.machine.mem_write(VALUES, struct.pack("<QI", value, numeric_type))
        fixture.begin_stream(); fixture.call(0x12d6f50, 1, FILE, VALUES)
        size = fixture.capture_stream()
        fixture.machine.mem_write(VALUES, struct.pack("<QI", 0, numeric_type))
        fixture.call(0x12d5cd0, 1, FILE, VALUES)
        restored = struct.unpack("<Q", fixture.machine.mem_read(VALUES, 8))[0]
        require(fixture.cursor == size and fixture.stream[fixture.cursor:] == struct.pack("<I", 0xdeadbeef),
                f"Type {numeric_type} crossed its stream boundary.")
        if numeric_type == 4:
            require(bytes(fixture.machine.mem_read(restored, 12)) == bytes(fixture.machine.mem_read(VECTOR, 12)), "Vector values differ.")
            allocation = fixture.allocations[-1]
            require(allocation["bytes"] == 16 and restored == allocation["address"] + 4, "Native vector allocation layout differs.")
            fixture.call(0x12e0030, 1, VALUES)
            require(fixture.frees[-1] == {"address": restored - 4, "bytes": 16}, "Native vector release differs.")
        elif numeric_type == 15:
            require(bytes(fixture.machine.mem_read(restored, 20)) == bytes(fixture.machine.mem_read(PACKED, 20)), "Empty packed stack differs.")
        elif numeric_type not in (0, 27):
            require(restored == value, f"Type {numeric_type} lost value bits.")
        cases.append({"type": numeric_type, "serializedBytes": size, "readSizes": list(fixture.read_sizes), "passed": True})
    return cases


def stack_case(capture, count):
    fixture = OwnedValues(capture)
    packed_size = 20 + count * 9
    packed = struct.pack("<QIHHI", fixture.code_pointer, 123, count, packed_size & 0xffff, 250000)
    ids = (65535, 65536, 129999, 250000)
    packed += b"".join(struct.pack("<BQ", 1, ids[index % len(ids)]) for index in range(count))
    fixture.machine.mem_write(PACKED, packed)
    fixture.begin_stream(); fixture.call(0x12d6da0, 1, FILE, PACKED)
    size = fixture.capture_stream()
    restored = fixture.call(0x12d5bc0, 1, FILE)
    require(bytes(fixture.machine.mem_read(restored, packed_size)) == packed, "Native packed stack lost an owner or value ID.")
    require(fixture.cursor == size, "Packed stack stream boundary differs.")
    allocated = fixture.allocations[-1]["bytes"]
    published = struct.unpack("<H", fixture.machine.mem_read(restored + 14, 2))[0]
    require(allocated == packed_size, "The native stack allocation differs.")
    require((published != allocated) == (count > 7279), "The expected native WORD byte-size boundary differs.")
    return {"count": count, "nativeAllocationBytes": allocated, "publishedWordBytes": published,
            "byteSizeTruncationObserved": published != allocated, "ownerId": 250000,
            "referenceIds": list(ids), "streamBytes": size, "sentinelUnread": True,
            "packedSha256": hashlib.sha256(packed).hexdigest()}


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
               "valueCases": value_cases(capture), "stackCases": [stack_case(capture, n) for n in (4, 7279, 7280)],
               "scope": __doc__, "activationAllowed": False}
    output.mkdir(parents=True)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("All 28 native value dispatches and three packed-stack boundary cases passed.")


if __name__ == "__main__":
    main()
