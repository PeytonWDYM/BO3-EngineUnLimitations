"""Exercise enrollment, normalized guards and the existing sampler on owned native processes."""
import argparse
from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pefile

REPO = Path(__file__).resolve().parents[3]
LIVE = REPO / "source/live"
sys.path.insert(0, str(LIVE))
sys.path.insert(0, str(LIVE / "vm"))
from windows_process import ACCESS_MASK, VerifiedProcess
from profile import validate
from enhanced_session import CapacitySite, resolve_enhanced_session, verify_code_evidence
from snapshot import sample
from latest_state import LatestState


class ReadTracking:
    def __init__(self, verified):
        self.verified = verified
        self.read_sizes = []
    def __getattr__(self, name):
        return getattr(self.verified, name)
    def read(self, address, size):
        self.read_sizes.append(size)
        return self.verified.read(address, size)


@contextmanager
def child(executable, mode):
    process = subprocess.Popen([str(executable), mode], cwd=executable.parent, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        ready = json.loads(process.stdout.readline())
        assert ready["pid"] == process.pid
        yield process, ready
    finally:
        if process.poll() is None:
            process.stdin.write("stop\n"); process.stdin.flush()
        _, errors = process.communicate(timeout=10)
        assert process.returncode == 0, errors


def mutate(process, command):
    process.stdin.write(command + "\n"); process.stdin.flush()
    assert process.stdout.readline().strip() == "changed"


def profile_for(executable):
    image = pefile.PE(str(executable))
    exports = {row.name.decode(): row.address for row in image.DIRECTORY_ENTRY_EXPORT.symbols if row.name}
    helper_path = executable.parent / "Bo3EnhancedHelper.dll"
    helper = pefile.PE(str(helper_path))
    helper_exports = {row.name.decode(): row.address for row in helper.DIRECTORY_ENTRY_EXPORT.symbols if row.name}
    state, code = exports["vmEnhancedState"], exports["vmEnhancedCode"]
    stock_code = bytes.fromhex("41b8d0fb0100") * 19 + bytes.fromhex("90cc")
    sites = tuple(CapacitySite(code + index * 6, bytes.fromhex("41b8d0fb0100"), 2) for index in range(19))
    profile = {
        "status": "fixture-only", "module": executable.name, "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "imageSize": image.OPTIONAL_HEADER.SizeOfImage, "timestamp": image.FILE_HEADER.TimeDateStamp,
        "poolPointerRva": state, "instancePointerStride": 32,
        "instances": [{"index": 0, "capacity": 130000}, {"index": 1, "capacity": 65000}],
        "slotStride": 64, "reservedZeroIndex": 0, "typeOffset": 8, "typeFormat": "I", "freeNumericType": 27,
        "linkOffset": 24, "linkFormat": "I", "reuseHead": {"slotIndex": 0, "offset": 24, "format": "I"},
        "deferredEntityHeadRva": state + 8, "deferredEntityHeadFormat": "I", "variablePublicInstanceStride": 32,
        "deferredEntityNumericType": 23, "firstErrorMessagePointerRva": state + 16,
        "firstErrorMessagePointerFormat": "Q", "errorMessageMaximumBytes": 1024,
        "currentFunctionDepthRva": state + 24, "currentFunctionDepthInstanceStride": 32,
        "currentFunctionDepthFormat": "I",
        "codeEvidence": [{"startRva": hex(code), "endRva": hex(code + len(stock_code)), "sha256": hashlib.sha256(stock_code).hexdigest()}],
        "enhancedHelper": {"sha256": hashlib.sha256(helper_path.read_bytes()).hexdigest(),
                           "bootRva": helper_exports["Bo3EnhancedBoot"], "stateBindingsRva": helper_exports["Bo3VmStateBindings"]},
    }
    return profile, sites


def receipt_for(process, ready):
    return {"schema": 1, "candidate": "0.1.0-test.3", "status": "ready", "processId": process.pid,
            "processCreatedFileTime": process.started_ticks, "imageBase": process.module.baseaddress,
            "helperBase": ready["helperBase"], "serverTotal": 500001, "clientTotal": 65000,
            "clientRoots": 18, "stockClientRoots": 8, "migrationBufferBytes": 33554432,
            "editsWritten": 42, "activated": True, "exited": False, "rollbackCompleted": False}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--fixture", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); output = args.output.resolve()
    assert not output.is_relative_to(REPO)
    base, sites = profile_for(args.fixture)
    source_files = [LIVE / "vm" / name for name in ("profile.py", "enhanced_session.py", "snapshot.py", "latest_state.py")]
    source_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}
    cases = []

    def refuses(name, operation, tracker):
        tracker.read_sizes.clear()
        try: operation()
        except (ValueError, OSError, KeyError, TypeError) as error:
            assert not any(size >= 65000 * 64 for size in tracker.read_sizes), "Refusal read a pool"
            cases.append({"name": name, "passed": True, "refused": str(error), "maximumReadBytes": max(tracker.read_sizes, default=0)})
        else: raise AssertionError(f"Missing refusal: {name}")

    for mode in ("stock", "enhanced"):
        with child(args.fixture, mode) as (native, ready), VerifiedProcess(native.pid, base) as verified:
            process = ReadTracking(verified)
            sessions = output / mode / "sessions"; sessions.mkdir(parents=True)
            path = sessions / f"{process.started_ticks}-{process.pid}.json"
            receipt = receipt_for(process, ready)
            assert resolve_enhanced_session(process, base, sessions, capacity_sites=sites) is None
            assert validate(base)[0].capacity == 130000
            cases.append({"name": f"{mode}-missing-receipt", "passed": True, "capacity": 130000})
            edited = copy.deepcopy(base); edited["instances"][0]["capacity"] = 500001
            refuses(f"{mode}-profile-only-expansion", lambda: validate(edited), process)
            path.write_text(json.dumps(receipt))
            stale_path = sessions / f"{process.started_ticks + 1}-{process.pid}.json"
            path.rename(stale_path)
            assert resolve_enhanced_session(process, base, sessions, capacity_sites=sites) is None
            stale_path.rename(path)
            cases.append({"name": f"{mode}-stale-filename", "passed": True, "capacity": 130000})
            if mode == "stock":
                refuses("stock-forged-ready-receipt", lambda: resolve_enhanced_session(process, base, sessions, capacity_sites=sites), process)
                path.unlink()
                verify_code_evidence(process, base)
                continue
            changes = (("pid", {"processId": process.pid + 1}), ("filetime", {"processCreatedFileTime": process.started_ticks + 1}),
                       ("status", {"status": "starting"}), ("candidate", {"candidate": "wrong"}), ("activated", {"activated": 1}),
                       ("edits", {"editsWritten": 41}), ("image", {"imageBase": process.module.baseaddress + 4096}),
                       ("helper", {"helperBase": ready["helperBase"] + 4096}), ("total", {"serverTotal": 1000001}),
                       ("client", {"clientTotal": 500001}), ("roots", {"clientRoots": 10}), ("migration", {"migrationBufferBytes": 1}),
                       ("schema-bool", {"schema": True}))
            for name, change in changes:
                path.write_text(json.dumps(receipt | change))
                refuses("receipt-" + name, lambda: resolve_enhanced_session(process, base, sessions, capacity_sites=sites), process)
            for name, data in (("truncated", b'{"schema":'), ("non-object", b'[]'), ("oversize", b' '*16385)):
                path.write_bytes(data)
                refuses("receipt-" + name, lambda: resolve_enhanced_session(process, base, sessions, capacity_sites=sites), process)
            path.write_text(json.dumps(receipt))
            wrong = copy.deepcopy(base); wrong["enhancedHelper"]["sha256"] = "0" * 64
            refuses("wrong-helper-hash", lambda: resolve_enhanced_session(process, wrong, sessions, capacity_sites=sites), process)
            refuses("missing-capacity-site", lambda: resolve_enhanced_session(process, base, sessions, capacity_sites=sites[:-1]), process)
            enrollment = resolve_enhanced_session(process, base, sessions, capacity_sites=sites)
            verify_code_evidence(process, base, enrollment)
            instances = validate(base, enhanced_session=enrollment)
            process.read_sizes.clear()
            reports, error, attempts = sample(process, base, instances, 1)
            assert error is None and reports[0]["capacity"] == 500001 and reports[0]["usableCapacity"] == 500000
            assert reports[0]["allocated"] == 3 and reports[0]["free"] == 499997
            assert reports[1]["capacity"] == 65000 and reports[1]["allocated"] == 3
            latest_path = output / "latest.json"; latest = LatestState(latest_path)
            latest.publish({"event": "sample", "utc": datetime.now(timezone.utc).isoformat(), "instances": reports})
            assert json.loads(latest_path.read_text())["lastSample"][0]["usableCapacity"] == 500000
            cases.append({"name": "enhanced-real-sample-and-latest", "passed": True, "accessMask": hex(ACCESS_MASK),
                          "pid": process.pid, "filetime": process.started_ticks, "attempts": attempts, "instances": reports,
                          "readSizes": process.read_sizes.copy()})
            (output / "profile.json").write_text(json.dumps(base, indent=2))
            (output / "session.json").write_text(json.dumps(receipt, indent=2))
            changed_profile = copy.deepcopy(base); changed_profile["instances"][1]["capacity"] = 130000
            refuses("changed-profile-enrollment", lambda: validate(changed_profile, enhanced_session=enrollment), process)
            refuses("serialized-enrollment", lambda: validate(base, enhanced_session=receipt), process)
            with VerifiedProcess(native.pid, base) as other_handle:
                refuses("different-process-handle", lambda: verify_code_evidence(other_handle, base, enrollment), process)
            mutate(native, "adjacent")
            refuses("unchanged-immediate-adjacent-byte", lambda: verify_code_evidence(process, base, enrollment), process)
            native.stdin.write("stop\n"); native.stdin.flush(); native.wait(timeout=10)
            refuses("exited-enrollment", lambda: validate(base, enhanced_session=enrollment), process)
    for mutation in ("partial", "opcode", "binding", "unreadable"):
        with child(args.fixture, "enhanced") as (native, ready), VerifiedProcess(native.pid, base) as verified:
            process = ReadTracking(verified); sessions = output / mutation / "sessions"; sessions.mkdir(parents=True)
            (sessions / f"{process.started_ticks}-{process.pid}.json").write_text(json.dumps(receipt_for(process, ready)))
            mutate(native, mutation)
            refuses("runtime-" + mutation, lambda: resolve_enhanced_session(process, base, sessions, capacity_sites=sites), process)
    assert source_hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}
    report = {"scope": "Owned native E2E only. Enrollment performs read-only capacity/helper checks before any expanded pool access.",
              "caseCount": len(cases), "cases": cases, "sources": source_hashes,
              "fixtureSha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
              "helperSha256": base["enhancedHelper"]["sha256"]}
    (output / "result.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__": main()
