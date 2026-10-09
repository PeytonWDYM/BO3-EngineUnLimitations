"""Exact job-receipt enrollment against the existing owned native VM pool fixture."""
import argparse
import copy
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("owned_late_enrollment", REPO / "source/tests/live-vm/Verify-LateSession.py")
late = importlib.util.module_from_spec(spec)
spec.loader.exec_module(late)
owned = late.owned
from enhanced_session import resolve_enhanced_session, verify_code_evidence
from profile import validate
from snapshot import sample
from windows_process import VerifiedProcess, kernel, require


def job_receipt(process, ready):
    receipt = owned.receipt_for(process, ready)
    for key in ("status", "activated", "exited"):
        receipt.pop(key)
    return receipt | {"startupMethod": "late-crt-job-freeze", "jobOwned": True,
        "jobMembershipVerified": True, "primaryOnlyAdmitted": True, "frozenForTransaction": True,
        "thawed": True, "committed": True, "released": True, "debuggerAbsent": True,
        "freezeStatus": 0, "thawStatus": 0, "threadsObserved": 1, "primaryThreadId": late.primary_thread(process.pid),
        "attached": False, "detached": False, "debugRegisterWrites": 0, "liveAllocationValidated": False,
        "terminated": False, "generation": 1, "gateBase": ready["helperBase"]}


def mutate_owned_helper(process, verified, address, data):
    """Write only a retained owned fixture's data record through a separate test handle."""
    assert process.pid == verified.pid and verified.path.name == "EnhancedOverlayFixture.exe" and verified.alive()
    write = kernel.WriteProcessMemory
    write.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                      ctypes.POINTER(ctypes.c_size_t)]
    write.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000 | 0x20 | 0x8, False, process.pid)
    require(handle, "OpenProcess owned mutation")
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        require(kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)), "GetProcessTimes mutation")
        assert (times[0].dwHighDateTime << 32 | times[0].dwLowDateTime) == verified.started_ticks
        written = ctypes.c_size_t()
        buffer = ctypes.create_string_buffer(data)
        require(write(handle, address, buffer, len(data), ctypes.byref(written)), "WriteProcessMemory owned data")
        assert written.value == len(data)
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.is_relative_to(REPO)
    profile, sites = owned.profile_for(args.fixture)
    cases = []

    def refuses(name, operation, process, *, no_runtime_reads=False):
        process.read_sizes.clear()
        try:
            operation()
        except (ValueError, OSError, KeyError, TypeError) as error:
            assert not any(size >= 65000 * 64 for size in process.read_sizes), "Refusal read a pool"
            if no_runtime_reads:
                assert not process.read_sizes, "Receipt selection refusal read runtime memory"
            cases.append({"name": name, "passed": True, "refused": str(error),
                          "pid": process.pid, "filetime": process.started_ticks, "readSizes": process.read_sizes.copy()})
        else:
            raise AssertionError("Missing refusal: " + name)

    for mode in ("stock", "enhanced"):
        with owned.child(args.fixture, mode) as (native, ready), VerifiedProcess(native.pid, profile) as verified:
            process = late.Tracked(verified)
            directory = output / mode / "sessions"
            directory.mkdir(parents=True)
            stem = f"{process.started_ticks}-{process.pid}"
            path = directory / f"{stem}-job.json"
            legacy_path, late_path = directory / f"{stem}.json", directory / f"{stem}-late.json"
            receipt = job_receipt(process, ready)
            enroll = lambda: resolve_enhanced_session(process, profile, directory, capacity_sites=sites)
            assert enroll() is None and validate(profile)[0].capacity == 130000
            stale = directory / f"{process.started_ticks + 1}-{process.pid}-job.json"
            stale.write_text(json.dumps(receipt))
            assert enroll() is None
            stale.unlink()
            cases.append({"name": mode + "-missing-and-stale-job-preserves-stock", "passed": True})
            path.write_text(json.dumps(receipt))
            if mode == "stock":
                refuses("stock-forged-job-receipt", enroll, process)
                continue

            # One representative per contract class. Each positive and negative runtime uses a native child.
            changes = {
                "ownership": {"jobOwned": False}, "membership": {"jobMembershipVerified": False},
                "primary": {"primaryOnlyAdmitted": False}, "freeze": {"frozenForTransaction": False},
                "thaw": {"thawed": False}, "commit": {"committed": False}, "release": {"released": False},
                "debugger": {"debuggerAbsent": False}, "freeze-status": {"freezeStatus": -1073741790},
                "thaw-status": {"thawStatus": 1}, "status-bool": {"freezeStatus": False},
                "thaw-status-bool": {"thawStatus": False}, "ownership-int": {"jobOwned": 1},
                "commit-int": {"committed": 1}, "thread-bool": {"threadsObserved": True},
                "threads-two": {"threadsObserved": 2}, "primary-zero": {"primaryThreadId": 0},
                "primary-bool": {"primaryThreadId": True}, "primary-overflow": {"primaryThreadId": 1 << 32},
                "gate-zero": {"gateBase": 0}, "gate-bool": {"gateBase": True},
                "attached": {"attached": True}, "detached": {"detached": True},
                "terminated": {"terminated": True}, "rollback": {"rollbackCompleted": True},
                "allocation-claim": {"liveAllocationValidated": True}, "register-write": {"debugRegisterWrites": 1},
                "register-bool": {"debugRegisterWrites": False}, "generation": {"generation": 2},
                "generation-bool": {"generation": True}, "edits": {"editsWritten": 41},
                "pid-reuse": {"processId": process.pid + 1}, "creation-reuse": {"processCreatedFileTime": process.started_ticks + 1},
                "image": {"imageBase": process.module.baseaddress + 4096}, "helper": {"helperBase": ready["helperBase"] + 4096},
                "server": {"serverTotal": 1000001}, "client": {"clientTotal": 500001},
                "roots": {"clientRoots": 8}, "stock-roots": {"stockClientRoots": 18},
                "migration": {"migrationBufferBytes": 1}, "schema-bool": {"schema": True},
                "candidate": {"candidate": "wrong"}, "stock-control": {"startupMethod": "late-crt-control"},
                "passive-control": {"startupMethod": "late-crt-passive-control"},
            }
            for name, change in changes.items():
                path.write_text(json.dumps(receipt | change))
                refuses("job-" + name, enroll, process)
            for missing in ("jobOwned", "jobMembershipVerified", "primaryOnlyAdmitted", "frozenForTransaction",
                            "thawed", "freezeStatus", "thawStatus", "threadsObserved", "primaryThreadId", "gateBase"):
                changed = receipt.copy()
                changed.pop(missing)
                path.write_text(json.dumps(changed))
                refuses("job-missing-" + missing, enroll, process)
            for name, data in (("truncated", b"{"), ("array", b"[]"), ("oversize", b" " * 16385)):
                path.write_bytes(data)
                refuses("job-" + name, enroll, process, no_runtime_reads=True)

            path.write_text(json.dumps(receipt))
            for second in (legacy_path, late_path):
                second.write_text("{")
                refuses("ambiguous-job-" + second.stem, enroll, process, no_runtime_reads=True)
                second.unlink()
            path.unlink()
            legacy_path.write_text(json.dumps(owned.receipt_for(process, ready)))
            late_path.write_text(json.dumps(late.late_receipt(process, ready)))
            refuses("legacy-late-ambiguity-preserved", enroll, process, no_runtime_reads=True)
            late_path.unlink()
            legacy = enroll()
            verify_code_evidence(process, profile, legacy)
            assert validate(profile, enhanced_session=legacy)[0].capacity == 500001
            legacy_path.unlink()
            late_path.write_text(json.dumps(late.late_receipt(process, ready)))
            old_late = enroll()
            verify_code_evidence(process, profile, old_late)
            assert validate(profile, enhanced_session=old_late)[0].capacity == 500001
            late_path.unlink()
            cases.append({"name": "legacy-and-late-positive-origins-preserved", "passed": True})

            path.write_text(json.dumps(receipt))
            wrong = copy.deepcopy(profile)
            wrong["enhancedHelper"]["sha256"] = "0" * 64
            refuses("job-wrong-helper-hash", lambda: resolve_enhanced_session(process, wrong, directory, capacity_sites=sites), process)
            process.on_read = lambda: path.write_text(json.dumps(receipt | {"thawed": False}))
            refuses("job-receipt-changes-during-enrollment", enroll, process)
            path.write_text(json.dumps(receipt))
            process.on_read = lambda: late_path.write_text("{")
            refuses("job-second-route-during-enrollment", enroll, process)
            late_path.unlink()
            enrollment = enroll()
            verify_code_evidence(process, profile, enrollment)
            instances = validate(profile, enhanced_session=enrollment)
            process.read_sizes.clear()
            reports, error, attempts = sample(process, profile, instances, 1)
            assert error is None and reports[0]["capacity"] == 500001 and reports[0]["usableCapacity"] == 500000
            assert reports[0]["allocated"] == 3 and reports[0]["free"] == 499997 and reports[1]["capacity"] == 65000
            cases.append({"name": "job-native-expanded-sample", "passed": True, "pid": process.pid,
                "filetime": process.started_ticks, "liveAllocationValidated": False,
                "attempts": attempts, "instances": reports, "readSizes": process.read_sizes.copy()})
            (output / "profile.json").write_text(json.dumps(profile, indent=2))
            (output / "job-session.json").write_text(json.dumps(receipt, indent=2))

            legacy_path.write_text("{")
            refuses("job-second-route-before-reverification", lambda: verify_code_evidence(process, profile, enrollment), process,
                    no_runtime_reads=True)
            legacy_path.unlink()
            process.on_read = lambda: legacy_path.write_text("{")
            refuses("job-second-route-during-reverification", lambda: verify_code_evidence(process, profile, enrollment), process)
            legacy_path.unlink()
            path.rename(late_path)
            refuses("job-selected-route-replaced", lambda: verify_code_evidence(process, profile, enrollment), process)
            late_path.rename(path)
            with VerifiedProcess(native.pid, profile) as other:
                refuses("job-different-handle", lambda: verify_code_evidence(other, profile, enrollment), process)
            changed = copy.deepcopy(profile)
            changed["instances"][1]["capacity"] = 130000
            refuses("job-profile-fingerprint-changed", lambda: validate(changed, enhanced_session=enrollment), process)
            refuses("job-serialized-receipt-not-authority", lambda: validate(profile, enhanced_session=receipt), process)
            native.stdin.write("stop\n")
            native.stdin.flush()
            native.wait(timeout=10)
            refuses("job-exited-enrollment", lambda: validate(profile, enhanced_session=enrollment), process)

    for mutation in ("partial", "opcode", "binding", "unreadable", "boot-ready", "boot-module", "callback-outside"):
        with owned.child(args.fixture, "enhanced") as (native, ready), VerifiedProcess(native.pid, profile) as verified:
            process = late.Tracked(verified)
            directory = output / mutation / "sessions"
            directory.mkdir(parents=True)
            (directory / f"{process.started_ticks}-{process.pid}-job.json").write_text(json.dumps(job_receipt(process, ready)))
            if mutation in ("partial", "opcode", "binding", "unreadable"):
                owned.mutate(native, mutation)
            elif mutation == "boot-ready":
                mutate_owned_helper(native, verified, ready["helperBase"] + profile["enhancedHelper"]["bootRva"] + 16,
                                    struct.pack("<I", 0))
            elif mutation == "boot-module":
                mutate_owned_helper(native, verified, ready["helperBase"] + profile["enhancedHelper"]["bootRva"] + 8,
                                    struct.pack("<Q", ready["helperBase"] + 4096))
            else:
                mutate_owned_helper(native, verified, ready["helperBase"] + profile["enhancedHelper"]["stateBindingsRva"] + 24,
                                    struct.pack("<Q", process.module.baseaddress))
            refuses("job-runtime-" + mutation,
                    lambda: resolve_enhanced_session(process, profile, directory, capacity_sites=sites), process)

    sources = [REPO / "source/live/vm/enhanced_session.py", REPO / "source/tests/vm/Verify-EnhancedSession.py",
               REPO / "source/tests/live-vm/Verify-LateSession.py", REPO / "source/tests/vm/EnhancedOverlayFixture.cpp",
               REPO / "source/tests/vm/EnhancedOverlayHelper.cpp"] + list(Path(__file__).parent.glob("*"))
    report = {"scope": "Owned native receipt enrollment only. No actual job transaction or BO3 launch.",
              "caseCount": len(cases), "cases": cases, "sources": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sources if path.is_file()}, "fixtureSha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
              "helperSha256": profile["enhancedHelper"]["sha256"]}
    (output / "result.json").write_text(json.dumps(report, indent=2))
    print(f"{len(cases)} owned job-enrollment cases passed.")


if __name__ == "__main__":
    main()
