"""Read-only enrollment E2E on an authored native process. No BO3 process is used."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import time

REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("owned_job", REPO / "source/tests/job-enrollment/Verify.py")
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)
owned, late = job.owned, job.late
from enhanced_session import resolve_enhanced_session, verify_code_evidence
from integrity_evidence import load_integrity_profile
from profile import validate
from snapshot import sample
from windows_process import ACCESS_MASK, VerifiedProcess
import pefile

ORIGINAL = {"Xor": bytes.fromhex("8b0c8b330c82"), "NegAdd": bytes.fromhex("8b0c8bf7d9030c82"),
            "Compare": bytes.fromhex("8b04828b148b3bc2"), "InputTransform": bytes.fromhex("8b0c8b330c82")}
REPLACEMENT = {"Xor": bytes.fromhex("8b0c8b31c990"), "NegAdd": bytes.fromhex("8b0c8b31c9909090"),
               "Compare": bytes.fromhex("8b04828b148b3bc0")}


def inventory(executable, output):
    profile, capacity = owned.profile_for(executable)
    pe = pefile.PE(str(executable))
    exports = {row.name.decode(): row.address for row in pe.DIRECTORY_ENTRY_EXPORT.symbols if row.name}
    start, context = exports["integrityCode"], exports["integrityContexts"]
    sites, contexts, original_digest, replacement_digest = [], [], hashlib.sha256(), hashlib.sha256()
    for index in range(1365):
        family = "Xor" if index < 247 else "NegAdd" if index < 506 else "Compare" if index < 1353 else "InputTransform"
        original = ORIGINAL[family]
        row = bytearray(b"\x90" * 40)
        row[:len(original)] = original
        row[16:24] = b"\0" * 8
        row[32] = index & 255
        rva = start + index * 64
        sites.append({"rva": rva, "family": family, "liveFlags": "ZeroCarry" if family == "Compare" else "Zero",
                      "guardSize": len(row), "guardSha256": hashlib.sha256(row).hexdigest(),
                      "imageAddresses": [{"offset": 16, "targetRva": exports["vmEnhancedCode"]}]})
        if family != "InputTransform":
            offset = 6 if family == "Compare" else 3
            header = struct.pack("<II", rva + offset, len(original) - offset)
            original_digest.update(header + original[offset:])
            replacement_digest.update(header + REPLACEMENT[family][offset:])
    for index in range(18):
        row = bytearray(b"\x90" * 40)
        row[:9] = bytes.fromhex("b80400000085c07400")
        row[16:24] = b"\0" * 8
        row[32] = index
        contexts.append({"rva": context + index * 64, "size": 40, "sha256": hashlib.sha256(row).hexdigest(),
                         "role": "owned-source-path", "imageAddresses": [{"offset": 16, "targetRva": start}]})
    manifest = {"schema": 1, "executableSha256": profile["sha256"], "timestamp": profile["timestamp"],
                "imageSize": profile["imageSize"], "module": executable.name,
                "regions": [{"rva": start, "size": 1365 * 64}, {"rva": context, "size": 18 * 64}],
                "patternCount": 1365, "editCount": 1353, "retainedTransformCount": 12,
                "sites": sites, "contextGuards": contexts, "productionInputAttributionVerified": True}
    path = output / "owned-integrity-profile.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    profile["integrityFixtureSha256"] = digest
    profile["codeEvidence"].append({"startRva": hex(start), "endRva": hex(start + 6),
                                    "sha256": hashlib.sha256(ORIGINAL["Xor"]).hexdigest()})
    return profile, capacity, path, (digest, original_digest.hexdigest(), replacement_digest.hexdigest())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-tool", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.is_relative_to(REPO)
    profile, capacity, manifest_path, digests = inventory(args.fixture, output)
    (output / "fixture-identities.json").write_text(json.dumps({"profileDigests": digests,
            "fixtureSha256": profile["sha256"], "helperSha256": profile["enhancedHelper"]["sha256"]}, indent=2))
    if args.prepare_only:
        return
    cases = []

    def refuses(name, operation, process, no_reads=False):
        process.read_sizes.clear()
        try:
            operation()
        except (ValueError, OSError, KeyError, TypeError) as error:
            assert not any(size >= 65000 * 64 for size in process.read_sizes), "Refusal read an expanded pool"
            if no_reads:
                assert not process.read_sizes, "Receipt refusal read runtime memory"
            cases.append({"name": name, "passed": True, "error": str(error), "readSizes": process.read_sizes.copy()})
        else:
            raise AssertionError("Missing refusal: " + name)

    for mode in ("stock", "enhanced"):
        with owned.child(args.fixture, mode) as (native, ready), VerifiedProcess(native.pid, profile) as verified:
            process = late.Tracked(verified)
            directory = output / mode / "sessions"
            directory.mkdir(parents=True)
            stem = f"{process.started_ticks}-{process.pid}"
            path = directory / f"{stem}-job.json"
            receipt = job.job_receipt(process, ready) | {
                "startupMethod": "late-crt-job-freeze-code-integrity", "editsWritten": 1395,
                "integrityProfile": digests[0], "integrityOriginalDigest": digests[1], "integrityReplacementDigest": digests[2],
                "integrityAdmitted": True, "integrityPatternsAdmitted": 1365, "integrityEditsPrepared": 1353,
                "integrityTransformsRetained": 12, "nativeEditsRequired": 42, "combinedEditsRequired": 1395,
                "integrityInputAttributionVerified": True, "integrityReapplication": False,
                "jobParentOnly": True, "killOnJobClose": True, "freezeAttempted": True, "thawAttempted": True,
                "relayFreed": False, "cleanupFailed": False, "runtimeMetadataReads": 4, "runtimeMetadataMask": 3,
                "stage": "released", "refusalReason": "", "unwindReason": "",
                "executableSha256": profile["sha256"], "helperSha256": profile["enhancedHelper"]["sha256"],
                "imagePath": str(process.path), "primaryPc": process.module.baseaddress + 1,
                "relay": process.module.baseaddress + 1, "frames": [process.module.baseaddress + 1],
                "threadObservations": [{"threadId": late.primary_thread(process.pid), "pc": process.module.baseaddress + 1,
                                        "start": process.module.baseaddress + 1}]}
            enroll = lambda: resolve_enhanced_session(process, profile, directory, capacity_sites=capacity, integrity_profile=manifest_path)
            assert enroll() is None
            path.write_text(json.dumps(receipt))
            if mode == "stock":
                refuses("stock-forged-integrity-receipt", enroll, process)
                continue
            refuses("retired-game-route-always-refused", lambda: resolve_enhanced_session(process,profile,directory,
                     capacity_sites=capacity),process,True)
            changes = {"attribution-false": {"integrityInputAttributionVerified": False},
                       "attribution-integer": {"integrityInputAttributionVerified": 1}, "admission-false": {"integrityAdmitted": False},
                       "profile": {"integrityProfile": "0" * 64}, "original": {"integrityOriginalDigest": "0" * 64},
                       "replacement": {"integrityReplacementDigest": "0" * 64}, "patterns": {"integrityPatternsAdmitted": 1364},
                       "edits": {"integrityEditsPrepared": 1352}, "transforms": {"integrityTransformsRetained": 11},
                       "native": {"nativeEditsRequired": 41}, "combined": {"combinedEditsRequired": 1394},
                       "written": {"editsWritten": 42}, "reapply": {"integrityReapplication": True},
                       "job": {"jobOwned": False}, "freeze": {"frozenForTransaction": False},
                       "metadata": {"runtimeMetadataMask": 1}, "cleanup": {"cleanupFailed": True},
                       "identity": {"processCreatedFileTime": process.started_ticks + 1},
                       "old-method": {"startupMethod": "late-crt-job-freeze"}}
            for name, change in changes.items():
                path.write_text(json.dumps(receipt | change))
                refuses(name, enroll, process, True)
            for key in ("integrityProfile", "integrityInputAttributionVerified", "integrityPatternsAdmitted", "runtimeMetadataReads"):
                missing = receipt.copy()
                missing.pop(key)
                path.write_text(json.dumps(missing))
                refuses("missing-" + key, enroll, process, True)
            path.write_text(json.dumps(receipt))
            for suffix in ("", "-late"):
                wrong = directory / f"{stem}{suffix}.json"
                path.rename(wrong)
                refuses("wrong-suffix" + suffix, enroll, process, True)
                wrong.rename(path)
            duplicate = directory / f"{stem}.json"
            duplicate.write_text("{")
            refuses("ambiguous-route", enroll, process, True)
            duplicate.unlink()
            process.on_read = lambda: path.write_text(json.dumps(receipt | {"thawed": False}))
            refuses("receipt-changed-during-reads", enroll, process)
            path.write_text(json.dumps(receipt))
            begin = time.perf_counter()
            enrollment = enroll()
            enrollment_ms = (time.perf_counter() - begin) * 1000
            verify_code_evidence(process, profile, enrollment)
            instances = validate(profile, enhanced_session=enrollment)
            process.read_sizes.clear()
            begin = time.perf_counter()
            reports, error, attempts = sample(process, profile, instances, 1, enhanced_session=enrollment)
            sample_ms = (time.perf_counter() - begin) * 1000
            assert error is None and reports[0]["capacity"] == 500001 and reports[0]["allocated"] == 3
            cases.append({"name": "owned-live-positive", "passed": True, "pid": process.pid, "filetime": process.started_ticks,
                          "accessMask": hex(ACCESS_MASK), "enrollmentMilliseconds": enrollment_ms,
                          "sampleMilliseconds": sample_ms, "reports": reports, "attempts": attempts,
                          "readSizes": process.read_sizes.copy(), "liveAllocationValidated": False})
            changed_profile = copy.deepcopy(profile)
            changed_profile["instances"][1]["capacity"] = 130000
            refuses("changed-profile-authority",lambda:validate(changed_profile,enhanced_session=enrollment),process,True)
            with VerifiedProcess(native.pid,profile) as second_handle:
                refuses("changed-process-handle",lambda:enrollment.authorize(profile,second_handle),process,True)
            path.write_text(json.dumps(receipt | {"thawed":False}))
            refuses("receipt-changed-after-enrollment",lambda:validate(profile,enhanced_session=enrollment),process,True)
            path.write_text(json.dumps(receipt))
            if args.receipt_tool:
                native_path = output / "native-serializer.json"
                subprocess.run([str(args.receipt_tool), str(process.pid), str(process.started_ticks),
                                str(process.module.baseaddress), str(ready["helperBase"]), str(late.primary_thread(process.pid)),
                                str(process.path), str(native_path)], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                serialized = json.loads(native_path.read_text())
                assert serialized["integrityProfile"] == digests[0] and serialized["integrityOriginalDigest"] == digests[1]
                path.write_bytes(native_path.read_bytes())
                if serialized["integrityInputAttributionVerified"]:
                    native_enrollment = enroll()
                    verify_code_evidence(process, profile, native_enrollment)
                    cases.append({"name": "real-native-serializer-live-acceptance", "passed": True})
                else:
                    refuses("real-native-serializer-false-attribution", enroll, process, True)
                path.write_text(json.dumps(receipt))
            owned.mutate(native, "restore")
            refuses("endpoint-restored-after-enrollment", lambda: validate(profile, enhanced_session=enrollment), process)
            process.read_sizes.clear()
            reports, error, _ = sample(process, profile, instances, 1, enhanced_session=enrollment)
            assert reports is None and error and not any(size >= 65000 * 64 for size in process.read_sizes)
            cases.append({"name": "ongoing-sample-refuses-before-pool", "passed": True, "error": error})
            native.stdin.write("stop\n")
            native.stdin.flush()
            native.wait(timeout=10)
            refuses("exited-process-authority",lambda:validate(profile,enhanced_session=enrollment),process,True)
    for mutation in ("restore", "prefix", "transform", "source", "path", "aslr", "partial", "binding", "boot", "unreadable"):
        with owned.child(args.fixture, "enhanced") as (native, ready), VerifiedProcess(native.pid, profile) as verified:
            process = late.Tracked(verified)
            directory = output / mutation / "sessions"
            directory.mkdir(parents=True)
            current = receipt | {"processId": process.pid, "processCreatedFileTime": process.started_ticks,
                                 "imageBase": process.module.baseaddress, "helperBase": ready["helperBase"],
                                 "gateBase": ready["helperBase"], "primaryThreadId": late.primary_thread(process.pid)}
            (directory / f"{process.started_ticks}-{process.pid}-job.json").write_text(json.dumps(current))
            owned.mutate(native, mutation)
            refuses("runtime-" + mutation, lambda: resolve_enhanced_session(process, profile, directory,
                    capacity_sites=capacity, integrity_profile=manifest_path), process)
    with owned.child(args.fixture, "legacy") as (native, ready), VerifiedProcess(native.pid, profile) as verified:
        process = late.Tracked(verified)
        directory = output / "old-origins" / "sessions"
        directory.mkdir(parents=True)
        stem = f"{process.started_ticks}-{process.pid}"
        for suffix, old_receipt in (("",owned.receipt_for(process,ready)),
                                    ("-late",late.late_receipt(process,ready)),
                                    ("-job",job.job_receipt(process,ready))):
            path = directory / f"{stem}{suffix}.json"
            path.write_text(json.dumps(old_receipt))
            enrollment = resolve_enhanced_session(process,profile,directory,capacity_sites=capacity)
            verify_code_evidence(process,profile,enrollment)
            instances = validate(profile,enhanced_session=enrollment)
            reports,error,_ = sample(process,profile,instances,1,enhanced_session=enrollment)
            assert error is None and reports[0]["capacity"] == 500001
            cases.append({"name":"preserved-origin"+(suffix or "-legacy"),"passed":True})
            path.unlink()
    report = {"scope": "Historical comparison prototype only. Authored native fixture and actual native receipt serializer. Success metadata is authored, not a startup transaction.",
              "limits": "No BO3 launch, AAE, migration, multiplayer or actual enhanced game allocation validation.",
              "cases": cases, "caseCount": len(cases), "profileDigests": digests,
              "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                          list(Path(__file__).parent.glob("*")) + [REPO / "source/live/vm" / n for n in
                          ("enhanced_session.py", "integrity_evidence.py", "snapshot.py", "Read-LiveVm.py")] if p.is_file()},
              "artifacts": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                            (args.fixture, args.fixture.parent / "Bo3EnhancedHelper.dll", manifest_path)}}
    (output / "result.json").write_text(json.dumps(report, indent=2))
    print(f"{len(cases)} read-only integrity enrollment cases passed.")


if __name__ == "__main__":
    main()
