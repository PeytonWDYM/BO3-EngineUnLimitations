"""Replay exact captured native per-slot codecs in owned emulator memory."""
import argparse
import hashlib
import json
import struct
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--manifest", type=Path, required=True)
parser.add_argument("--executable", type=Path, required=True)
parser.add_argument("--dependencies", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--usable", type=int, default=500000, choices=(129999, 500000, 1000000))
args = parser.parse_args()
sys.path.insert(0, str(args.dependencies))
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RSP, UC_X86_REG_RIP, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_RAX

EXPECTED = "0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0"
assert hashlib.file_digest(args.executable.open("rb"), "sha256").hexdigest() == EXPECTED
output = args.output.resolve()
repo = Path(__file__).resolve().parents[3]
assert not output.is_relative_to(repo), "Keep private replay artifacts outside the repository"
output.mkdir(exist_ok=False)
meta = json.loads(args.manifest.read_text())
base = int(meta["baseAddress"], 0)
image = bytearray(meta["imageSize"])
for item in meta["ranges"]:
    raw = (args.manifest.parent / item["file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    start = int(item["moduleOffset"], 0)
    image[start:start + len(raw)] = raw

POOL, HASH, STACK, DRIVER, FILE = 0x40000000, 0x48000000, 0x50000000, 0x51000000, 0x52000000
STOP = DRIVER + 0x800
CHUNK = 0x3FFF8


def run(kind):
    total = args.usable + 1
    u = Uc(UC_ARCH_X86, UC_MODE_64)
    for rva, size in ((0x12D5000, 0x3000), (0x12D9000, 0xB000), (0x5124000, 0x1000),
                      (0x35EE000, 0x1000), (0x2277000, 0x1000), (0xD2000, 0x1000), (0x2BC3000, 0x1000)):
        u.mem_map(base + rva, size)
        u.mem_write(base + rva, bytes(image[rva:rva + size]))
    for address, size in ((POOL, (total * 64 + 4095) & ~4095), (HASH, 0x40000),
                          (STACK, 0x10000), (DRIVER, 0x1000), (FILE, 0x41000)):
        u.mem_map(address, size)
    u.mem_write(base + 0x5124580, struct.pack("<Q", POOL))
    u.mem_write(base + 0x5124500, struct.pack("<Q", HASH))
    pool = bytearray(total * 64)
    buckets = bytearray(0x40000)
    struct.pack_into("<I", pool, 24, 2 if kind == "sparse" else 0)
    for slot in range(1, total):
        offset = slot * 64
        occupied = kind == "dense" or slot in (1, 129999, min(262144, total - 1), total - 1)
        if not occupied:
            struct.pack_into("<I", pool, offset + 8, 27)
            next_id = slot + 1
            while next_id < total and next_id in (129999, min(262144, total - 1), total - 1):
                next_id += 1
            struct.pack_into("<I", pool, offset + 24, next_id if next_id < total else 0)
            continue
        # Type 7 uses the native scalar value branch. Higher names remain full 64-bit keys.
        struct.pack_into("<QI", pool, offset, slot * 3, 7)
        struct.pack_into("<I", pool, offset + 16, 0x101)
        key, parent = slot + 0x100000, 1
        struct.pack_into("<Q", pool, offset + 40, key)
        struct.pack_into("<I", pool, offset + 56, parent)
        bucket = (parent * 101 + key) & 0xFFFF
        old = struct.unpack_from("<I", buckets, bucket * 4)[0]
        struct.pack_into("<I", pool, offset + 60, old)
        struct.pack_into("<I", buckets, bucket * 4, slot)
    original = bytes(pool)
    u.mem_write(POOL, original)
    u.mem_write(HASH, bytes(buckets))
    chunks = []
    reading = False
    offset = 0
    read_calls = 0
    native_inserts = 0

    def ret():
        stack = u.reg_read(UC_X86_REG_RSP)
        target = struct.unpack("<Q", u.mem_read(stack, 8))[0]
        u.reg_write(UC_X86_REG_RSP, stack + 8)
        u.reg_write(UC_X86_REG_RIP, target)

    def flush():
        length = struct.unpack("<I", u.mem_read(FILE + 24, 4))[0]
        chunks.append(bytes(u.mem_read(FILE + 56, length)))
        u.mem_write(FILE + 24, b"\0" * 4)

    def stub(engine, address, size, unused):
        nonlocal offset, read_calls
        rva = address - base
        if rva == 0x2277A60:
            assert not reading and engine.reg_read(UC_X86_REG_RCX) == FILE
            flush()
        elif rva in (0xD27C0, 0xD2870, 0xD2700):
            assert not reading and engine.reg_read(UC_X86_REG_RCX) == FILE
            length = struct.unpack("<I", engine.mem_read(FILE + 24, 4))[0]
            primitive_size = 8 if rva == 0xD27C0 else 4
            if length + primitive_size >= CHUNK:
                flush()
                length = 0
            value = engine.reg_read(UC_X86_REG_RDX)
            engine.mem_write(FILE + 56 + length, struct.pack("<Q", value)[:primitive_size])
            engine.mem_write(FILE + 24, struct.pack("<I", length + primitive_size))
        elif rva == 0x22778B0:
            assert reading and engine.reg_read(UC_X86_REG_RCX) == FILE
            count = engine.reg_read(UC_X86_REG_RDX)
            assert offset + count <= len(data), "native reader passed end of stream"
            target = engine.reg_read(UC_X86_REG_R8)
            engine.mem_write(target, data[offset:offset + count])
            offset += count
            read_calls += 1
        elif rva != 0x2BC3AA0:
            raise AssertionError(f"Unexpected owned stub {rva:x}")
        ret()

    for rva in (0x2277A60, 0xD27C0, 0xD2870, 0xD2700, 0x22778B0, 0x2BC3AA0):
        u.hook_add(UC_HOOK_CODE, stub, begin=base + rva, end=base + rva)

    def count_insert(engine, address, size, unused):
        nonlocal native_inserts
        native_inserts += 1

    u.hook_add(UC_HOOK_CODE, count_insert, begin=base + 0x12D9420, end=base + 0x12D9420)

    def drive(function):
        # Owned Windows x64 caller. Every slot call executes the captured native codec.
        code = bytearray(b"\x48\x83\xec\x28\x41\xbc" + struct.pack("<I", args.usable) + b"\x41\xbd\x01\x00\x00\x00")
        loop = len(code)
        code += b"\x31\xc9\x48\xba" + struct.pack("<Q", FILE) + b"\x45\x89\xe8\x48\xb8" + struct.pack("<Q", base + function)
        code += b"\xff\xd0\x41\xff\xc5\x41\xff\xcc\x75"
        code += struct.pack("b", loop - (len(code) + 1)) + b"\x48\x83\xc4\x28\xc3"
        u.mem_write(DRIVER, bytes(code))
        u.ctl_remove_cache(DRIVER, DRIVER + 0x1000)
        stack = STACK + 0x8008
        u.mem_write(stack, struct.pack("<Q", STOP))
        u.reg_write(UC_X86_REG_RSP, stack)
        try:
            u.emu_start(DRIVER, STOP, count=300000000)
        except Exception:
            print("native-replay-failure", hex(u.reg_read(UC_X86_REG_RIP)), flush=True)
            print("read-offset", offset, "read-calls", read_calls, "stream-prefix", data[:96].hex() if reading else "writing", flush=True)
            raise
        assert u.reg_read(UC_X86_REG_RIP) == STOP

    started = time.monotonic()
    drive(0x12D64C0)
    flush()
    data = b"".join(chunks)
    (output / f"{kind}-native-slot-stream.bin").write_bytes(data)
    u.mem_write(POOL, b"\0" * len(pool))
    u.mem_write(HASH, b"\0" * len(buckets))
    reading = True
    drive(0x12D5590)
    assert offset == len(data), (offset, len(data))
    restored = bytes(u.mem_read(POOL, len(pool)))
    # Slot zero is outside these per-slot functions. Its free head belongs to the adapter prefix.
    assert restored[64:] == original[64:]
    assert bytes(u.mem_read(HASH, len(buckets))) == bytes(buckets)
    result = {"kind": kind, "usable": args.usable, "serializedSlotBytes": len(data),
              "readPrimitiveCalls": read_calls, "nativeHashInsertions": native_inserts,
              "slotStreamSha256": hashlib.sha256(data).hexdigest(),
              "restoredPoolSha256": hashlib.sha256(restored[64:]).hexdigest(),
              "elapsedSeconds": round(time.monotonic() - started, 3)}
    print(json.dumps(result), flush=True)
    return result


results = [run("sparse"), run("dense")]
receipt = {"sourceSha256": EXPECTED, "manifestSha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
           "harnessSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "cases": results,
           "scope": "Native per-slot writer, reader, typed scalar decoder, hash lookup and hash insertion. Owned memory-file primitive and security-cookie stubs. No game process, strings, vectors, suspended stacks, native compression or whole-state tail execution."}
(output / "result.json").write_text(json.dumps(receipt, indent=2))
