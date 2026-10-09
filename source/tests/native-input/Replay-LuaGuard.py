"""Replay one private native Lua entry without executing game or mod initialization."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

import pefile
from unicorn import Uc, UcError, UC_ARCH_X86, UC_HOOK_CODE, UC_HOOK_MEM_WRITE_UNMAPPED, UC_MODE_64
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_GS_BASE, UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_RIP, UC_X86_REG_RSP


def replay(path: Path, profile: dict, state: str, depth: int = 0, result: int = 0, delta: int = 0) -> dict:
    pe = pefile.PE(str(path))
    base = pe.OPTIONAL_HEADER.ImageBase + delta
    memory = Uc(UC_ARCH_X86, UC_MODE_64)
    memory.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    memory.mem_write(base, pe.get_memory_mapped_image())
    scratch = 0x20000000
    stack = 0x30000000
    stubs = 0x40000000
    memory.mem_map(scratch, 0x20000)
    memory.mem_map(stack, 0x20000)
    memory.mem_map(stubs, 0x1000)
    memory.mem_write(stubs, b"\xc3" * 0x1000)
    state_address, global_address = scratch, scratch + 0x2000
    teb, tls_offset, locks = scratch + 0x4000, scratch + 0x6000, scratch + 0x8000
    memory.reg_write(UC_X86_REG_GS_BASE, teb)
    memory.mem_write(teb + 0x30, struct.pack("<Q", teb))
    memory.mem_write(state_address + 0x10, struct.pack("<Q", global_address if state == "ready" else 0))
    memory.mem_write(state_address + 0xA0, struct.pack("<Q", scratch + 0xA000))
    memory.mem_write(scratch + 0xA004, struct.pack("<I", 61))
    counter = teb + 0x108 + 61 * 4
    memory.mem_write(counter, struct.pack("<I", depth))
    for name, value in (("state", 0 if state == "absent" else state_address), ("tlsOffset", tls_offset), ("locks", locks)):
        memory.mem_write(base + profile["globals"][name], struct.pack("<Q", value))
    callback_names = ["enter", "leave", "compile", "protectedCall", "destroyString", "cookie", "report"]
    callback_addresses = {stubs + 16 * index: name for index, name in enumerate(callback_names)}
    for name in ("enter", "leave", "compile", "protectedCall"):
        address = next(address for address, label in callback_addresses.items() if label == name)
        memory.mem_write(base + profile["callbacks"][name], struct.pack("<Q", address))
    for name in ("destroyString", "cookie", "report"):
        callback_addresses[base + profile["callbacks"][name]] = name
    calls: list[str] = []
    writes: list[int] = []
    stop = stubs + 0xF00

    def on_code(engine: Uc, address: int, size: int, user_data: object) -> None:
        if address == stop:
            engine.emu_stop()
            return
        name = callback_addresses.get(address)
        if name is None:
            return
        calls.append(name)
        # The verified MSVC cookie leaf preserves the function's return register.
        if name != "cookie":
            engine.reg_write(UC_X86_REG_RAX, result if name == "protectedCall" else 0)
        rsp = engine.reg_read(UC_X86_REG_RSP)
        return_address = struct.unpack("<Q", engine.mem_read(rsp, 8))[0]
        engine.reg_write(UC_X86_REG_RSP, rsp + 8)
        engine.reg_write(UC_X86_REG_RIP, return_address)

    def on_bad_write(engine: Uc, access: int, address: int, size: int, value: int, user_data: object) -> bool:
        writes.append(address)
        return False

    memory.hook_add(UC_HOOK_CODE, on_code)
    memory.hook_add(UC_HOOK_MEM_WRITE_UNMAPPED, on_bad_write)
    rsp = stack + 0x10008
    memory.mem_write(rsp, struct.pack("<Q", stop))
    memory.reg_write(UC_X86_REG_RSP, rsp)
    memory.reg_write(UC_X86_REG_RCX, scratch + 0xC000)
    memory.reg_write(UC_X86_REG_RDX, scratch + 0xD000)
    error = None
    try:
        memory.emu_start(base + profile["entry"], stop, count=2000)
    except UcError as exception:
        error = str(exception)
    return {
        "state": state, "initialDepth": depth, "calls": calls, "invalidWrites": writes, "emulatorError": error,
        "finalDepth": struct.unpack("<I", memory.mem_read(counter, 4))[0],
        "sharingMode": struct.unpack("<Q", memory.mem_read(global_address + 0x1D8, 8))[0],
        "return": memory.reg_read(UC_X86_REG_EAX), "returned": memory.reg_read(UC_X86_REG_RIP) == stop,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    if hashlib.sha256(args.original.read_bytes()).hexdigest() != profile["sourceSha256"]:
        raise ValueError("The replay original differs from the private profile.")
    output = args.output.resolve()
    repo = Path(__file__).resolve().parents[3]
    if output == repo or repo in output.parents or output.exists():
        raise ValueError("Use a new private replay output directory.")
    output.mkdir(parents=True)
    original = replay(args.original, profile, "unavailable")
    assert original["invalidWrites"] == [0x1D8], original
    report = {"originalSha256": profile["sourceSha256"], "originalFailure": original, "scope": "Native instruction emulation with owned memory and mocked external calls. No game execution, actual lock implementation, or live lifetime race validation."}
    if args.candidate:
        cases = []
        for state, depth, result, delta in [("unavailable", 0, 0, 0), ("unavailable", 2, 0, 0), ("absent", 0, 0, 0), ("ready", 0, 0, 0), ("ready", 2, 0, 0), ("ready", 0, 37, 0), ("ready", 0, 0, 0x1000000)]:
            actual = replay(args.candidate, profile, state, depth, result, delta)
            assert actual["emulatorError"] is None and actual["returned"], actual
            assert actual["finalDepth"] == depth, actual
            if state == "ready":
                baseline = replay(args.original, profile, state, depth, result, delta)
                assert actual == baseline, (actual, baseline)
                assert actual["sharingMode"] == 2 and actual["return"] == result, actual
            else:
                expected = ["destroyString", "cookie"]
                if state == "unavailable" and depth == 0:
                    expected = ["enter", "leave"] + expected
                assert actual["calls"] == expected and actual["return"] == 0, actual
            cases.append(actual)
        report["candidateSha256"] = hashlib.sha256(args.candidate.read_bytes()).hexdigest()
        report["cases"] = cases
    (output / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"passed": True, "candidateCases": len(report.get("cases", [])), "output": str(output)}))


if __name__ == "__main__":
    main()
