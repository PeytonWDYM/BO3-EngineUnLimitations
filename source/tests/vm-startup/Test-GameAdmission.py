"""Check captured code as read-only data in an owned Windows child. No BO3 instruction executes."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import struct

EXPECTED = "0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0"
REPO = Path(__file__).resolve().parents[3]


def kernel():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.VirtualAlloc.argtypes = (ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD)
    api.VirtualAlloc.restype = ctypes.c_void_p
    api.VirtualProtect.argtypes = (ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    api.VirtualProtect.restype = wintypes.BOOL
    api.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    api.OpenProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = (wintypes.HANDLE,)
    api.CloseHandle.restype = wintypes.BOOL
    return api


def child(blocks, image_size, timestamp, scenario, channel, done):
    try:
        api = kernel()
        base = api.VirtualAlloc(None, image_size, 0x2000, 1)
        assert base, ctypes.WinError(ctypes.get_last_error())
        pages = {0, 0x3EC4000, 0x5124000}
        for rva, data in blocks:
            pages.update(range(rva & ~4095, (rva + len(data) + 4095) & ~4095, 4096))
        for page in pages:
            assert api.VirtualAlloc(base + page, 4096, 0x1000, 4)
        header = bytearray(512)
        header[:2] = b"MZ"
        struct.pack_into("<I", header, 0x3C, 0x80)
        header[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", header, 0x84, 0x8664)
        struct.pack_into("<I", header, 0x88, timestamp + (scenario == "pe-drift"))
        struct.pack_into("<H", header, 0x98, 0x20B)
        struct.pack_into("<I", header, 0xD0, image_size)
        ctypes.memmove(base, bytes(header), len(header))
        for rva, data in blocks:
            ctypes.memmove(base + rva, data, len(data))
        if scenario == "code-drift":
            address = base + blocks[0][0] + len(blocks[0][1]) - 1
            ctypes.c_ubyte.from_address(address).value ^= 0x80
        if scenario == "migration-exists":
            ctypes.c_uint64.from_address(base + 0x3EC4ED8).value = 0x12340000
        if scenario == "capacity-exists":
            ctypes.c_uint32.from_address(base + 0x3EC4EF8).value = 0x280000
        for page in pages:
            old = wintypes.DWORD()
            assert api.VirtualProtect(base + page, 4096, 2, ctypes.byref(old))

        def digest():
            value = hashlib.sha256()
            for page in sorted(pages):
                value.update(ctypes.string_at(base + page, 4096))
            return value.hexdigest()

        channel.send({"base": base, "before": digest(), "readOnlyPages": len(pages)})
        assert done.wait(20), "Owned parent did not complete its read."
        channel.send({"after": digest()})
    except Exception as exc:
        channel.send({"error": str(exc)})
        raise
    finally:
        channel.close()


class AdmissionResult(ctypes.Structure):
    _fields_ = [("accepted", ctypes.c_uint32), ("countEdits", ctypes.c_uint32),
               ("codeGuards", ctypes.c_uint32), ("error", ctypes.c_char * 256)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "executable", "fixture", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.is_relative_to(REPO)
    assert not output.exists()
    inventory_path = REPO / "source/patches/vm_pool/exact_build_inventory.json"
    inventory = json.loads(inventory_path.read_text())
    meta = json.loads(args.manifest.read_text())
    with args.executable.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == EXPECTED
    parts = []
    for row in meta["ranges"]:
        data = (args.manifest.parent / row["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        parts.append((int(row["moduleOffset"], 0), data))
    blocks = []
    for guard in inventory["codeGuards"]:
        start, end = guard["rva"], guard["rva"] + guard["size"]
        matches = [(offset, data) for offset, data in parts if offset <= start and end <= offset + len(data)]
        assert len(matches) == 1
        offset, data = matches[0]
        body = data[start-offset:end-offset]
        if start == 0x20EC0B0:
            body = bytes.fromhex(inventory["nativeHooks"][3]["original5"]) + body[5:]
        assert hashlib.sha256(body).hexdigest() == guard["sha256"]
        blocks.append((start, body))
    library = ctypes.WinDLL(str(args.fixture.resolve()))
    check = library.CheckGameAdmission
    check.argtypes = (wintypes.HANDLE, ctypes.c_size_t, ctypes.c_uint32, ctypes.POINTER(AdmissionResult))
    check.restype = None
    api = kernel()
    context = mp.get_context("spawn")
    receipts = []
    cases = [("exact", 500001), ("exact", 1000001), ("code-drift", 500001), ("pe-drift", 500001),
             ("migration-exists", 500001), ("capacity-exists", 500001), ("unsupported-capacity", 130000)]
    for scenario, total in cases:
        parent, remote = context.Pipe()
        done = context.Event()
        target = context.Process(target=child, args=(blocks, inventory["imageSize"], inventory["timestamp"], scenario, remote, done))
        target.start()
        remote.close()
        handle = None
        try:
            assert parent.poll(15), "Owned child did not publish its data."
            trace = parent.recv()
            assert "error" not in trace, trace
            handle = api.OpenProcess(0x1010, False, target.pid)
            assert handle, ctypes.WinError(ctypes.get_last_error())
            result = AdmissionResult()
            check(handle, trace["base"], total, ctypes.byref(result))
            expected = scenario == "exact"
            assert bool(result.accepted) == expected, (scenario, result.error)
            if scenario == "unsupported-capacity":
                assert not result.countEdits
            else:
                assert result.codeGuards == len(blocks) and result.countEdits == 19
            done.set()
            assert parent.poll(15)
            after = parent.recv()
            assert trace["before"] == after["after"]
            target.join(10)
            assert target.exitcode == 0
            receipts.append({"scenario": scenario, "total": total, "passed": True, "accepted": bool(result.accepted),
                             "countEdits": result.countEdits, "codeGuards": result.codeGuards, "error": result.error.decode(),
                             "readOnlyPages": trace["readOnlyPages"], "unchangedSha256": after["after"]})
        finally:
            done.set()
            if handle:
                api.CloseHandle(handle)
            if target.is_alive():
                target.terminate()
                target.join(10)
            parent.close()
    sources = [inventory_path, Path(__file__), Path(__file__).with_name("GameAdmissionShim.cpp"),
               Path(__file__).with_name("Build-GameAdmission.ps1"), Path(__file__).with_name("GameAdmissionFailures.txt")]
    sources += list((REPO / "source/launch/enhanced").glob("GameProfile.*"))
    sources.append(REPO / "source/launch/enhanced/Generate-GameProfile.py")
    report = {"scope": "Compiled admission against captured bytes stored as read-only data in owned children. No captured instruction or BO3 process executes.",
              "caseCount": len(receipts), "receipts": receipts,
              "sources": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
              "fixtureSha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest()}
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"caseCount": len(receipts), "passed": True, "output": str(output)}))


if __name__ == "__main__":
    main()
