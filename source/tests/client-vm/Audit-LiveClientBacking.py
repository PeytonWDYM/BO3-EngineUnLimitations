"""Read an exact private process's native VM arena metadata with VM_READ only."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from native_capture import NativeCapture, require, EXACT_EXECUTABLE

PRIVATE_GAME = Path("C:/Users/plamb/.codex/labs/bo3-engine/deep-capacity-game-20261010/steamapps/common/BlackOps3/BlackOps3.exe")
PROCESS_READER = Path("C:/Users/plamb/Desktop/project/All Around Enhancement Enhanced/source/live")
HEADER_RVA = 0x166EAE10 + 2 * 0xF68


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--start-ticks", type=int, required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--client-total", type=int, choices=(65000, 250001), default=65000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Keep each observation receipt immutable.")
    capture = NativeCapture(args.manifest, args.executable)
    sys.path.insert(0, str(PROCESS_READER))
    from windows_process import VerifiedProcess, ACCESS_MASK
    require(ACCESS_MASK == 0x1010, "The process reader must use query and VM_READ only.")
    profile = {"module": "BlackOps3.exe", "sha256": EXACT_EXECUTABLE,
               "timestamp": 1765634846, "imageSize": 494186496}
    with VerifiedProcess(args.pid, profile, args.start_ticks) as process:
        require(process.path.samefile(PRIVATE_GAME), "The process is outside the authorized private game.")
        base = process.module.baseaddress
        inventory = json.loads((Path(__file__).resolve().parents[2] / 'patches/client_vm/exact_build_inventory.json').read_text())
        require(len(inventory['clientCountInstructions']) == 19, 'The client count inventory is incomplete.')
        for instruction in inventory['clientCountInstructions']:
            expected = bytearray.fromhex(instruction['bytes'])
            require(capture.read(instruction['rva'], len(expected)) == bytes(expected),
                    'The original captured client count instruction differs.')
            struct.pack_into('<I', expected, instruction['immediateOffset'], args.client_total)
            require(process.read(base + instruction['rva'], len(expected)) == bytes(expected),
                    'A complete native client count differs from the declared capacity.')
        guards = []
        # These instructions select type2/subpool0 and check the arena cursor.
        for rva, size in ((0x12DF25A, 6), (0x12DF281, 14), (0x20C5FD8, 0x2C), (0x20C60B5, 0x92)):
            expected = capture.read(rva, size)
            require(process.read(base + rva, size) == expected, "A native allocator guard differs.")
            guards.append({"rva": rva, "bytes": size, "sha256": hashlib.sha256(expected).hexdigest()})
        header = process.read(base + HEADER_RVA, 0xF68)
        cursor = struct.unpack_from("<Q", header, 0x10)[0]
        descriptor = struct.unpack_from("<Q", header, 0xF40)[0]
        fields = process.read(descriptor, 0x28)
        mode, = struct.unpack_from("<I", fields)
        name, arena, reserved = struct.unpack_from("<QQQ", fields, 8)
        require(mode == 2 and 0 < cursor <= reserved, "The native arena descriptor differs.")
        arena_name = process.read(name, 64).split(b"\0", 1)[0].decode("ascii")
        pools = []
        for instance, total in ((0, 500001), (1, args.client_total)):
            pool = process.number(base + 0x5124580 + instance * 0x100, "Q")
            table = process.number(base + 0x5124500 + instance * 0x100, "Q")
            pool_offset, table_offset = pool - arena, table - arena
            require(0 <= pool_offset < pool_offset + total * 64 <= cursor,
                    "VM backing is outside the allocated native arena span.")
            # Native allocation uses 65536 DWORD hash buckets for either instance.
            require(0 <= table_offset < table_offset + 0x40000 <= cursor,
                    "VM hash backing is outside the allocated native arena span.")
            pools.append({"instance": instance, "total": total, "slotAddress": pool,
                          "slotBytes": total * 64, "slotArenaOffset": pool_offset,
                          "hashAddress": table, "hashBytes": 0x40000, "hashArenaOffset": table_offset})
        require(process.read(base + HEADER_RVA, 0xF68) == header,
                "The allocator header changed during the observation.")
        require(process.alive(), "The private process exited during the observation.")
        result = {"scope": "Read-only exact client-count/server500K arena observation. Reserved headroom is not peak map demand, committed memory, or complete lifetime proof.",
                  "clientTotal": args.client_total, "clientCountInstructionsVerified": 19,
                  "pid": args.pid, "processCreatedFileTime": args.start_ticks, "phase": args.phase,
                  "executableSha256": process.sha256, "baseAddress": base,
                  "nativeAllocatorGuards": guards, "headerRva": HEADER_RVA,
                  "headerSha256": hashlib.sha256(header).hexdigest(), "memoryType": 2, "subpool": 0,
                  "descriptorAddress": descriptor, "descriptorSha256": hashlib.sha256(fields).hexdigest(),
                  "mode": mode, "arenaName": arena_name, "arenaBase": arena, "reservedBytes": reserved,
                  "cursorBytes": cursor, "reservedHeadroomBytes": reserved - cursor,
                  "client250001AdditionalSlotBytes": (250001 - 65000) * 64,
                  "pools": pools, "accessMask": ACCESS_MASK, "passed": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
