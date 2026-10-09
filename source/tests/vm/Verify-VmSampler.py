"""Run the CLI against owned native processes and retain repeatable E2E evidence."""

import argparse
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback

import pefile

REPO = Path(__file__).resolve().parents[3]
LIVE = REPO / "source" / "live"
sys.path.insert(0, str(LIVE))
from windows_process import VerifiedProcess

CLI = LIVE / "vm" / "Read-LiveVm.py"


@contextmanager
def fixture(executable, mode):
    process = subprocess.Popen([str(executable), mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        ready = json.loads(process.stdout.readline())
        assert ready["pid"] == process.pid
        yield process, ready
    finally:
        if process.poll() is None:
            process.stdin.write("stop\n")
            process.stdin.flush()
        process.communicate(timeout=10)
        assert process.returncode == 0, f"Fixture exit: {process.returncode}"


def command(process, value):
    process.stdin.write(value + "\n")
    process.stdin.flush()
    return process.stdout.readline().strip()


def profile_for(executable):
    pe = pefile.PE(str(executable))
    state = next(symbol.address for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols if symbol.name == b"vmFixtureState")
    return {
        "status": "fixture-only", "module": executable.name,
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "imageSize": pe.OPTIONAL_HEADER.SizeOfImage, "timestamp": pe.FILE_HEADER.TimeDateStamp,
        "poolPointerRva": state, "instancePointerStride": 0,
        "instances": [{"index": 0, "capacity": 256}],
        "slotStride": 64, "reservedZeroIndex": 0, "typeOffset": 8, "typeFormat": "I",
        "freeNumericType": 27, "linkOffset": 24, "linkFormat": "I",
        "reuseHead": {"slotIndex": 0, "offset": 24, "format": "I"},
        "deferredEntityHeadRva": state + 8, "deferredEntityHeadFormat": "I",
        "variablePublicInstanceStride": 0, "deferredEntityNumericType": 23,
        "firstErrorMessagePointerRva": state + 16, "firstErrorMessagePointerFormat": "Q",
        "errorMessageMaximumBytes": 1024,
        "currentFunctionDepthRva": state + 24, "currentFunctionDepthInstanceStride": 0,
        "currentFunctionDepthFormat": "I",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert REPO != output and REPO not in output.parents
    base = profile_for(args.fixture)
    cases = []
    sequence = 0

    def capture(process, name, profile=None, expected=None, duration=0.22):
        nonlocal sequence
        sequence += 1
        directory = output / f"{sequence:02d}-{name}"
        directory.mkdir()
        profile = copy.deepcopy(profile or base)
        profile_path = directory / "profile.json"
        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        rows_path = directory / "samples.jsonl"
        argv = [sys.executable, str(CLI), "--pid", str(process.pid), "--profile", str(profile_path),
                "--output", str(rows_path), "--rate", "10", "--duration", str(duration), "--attempts", "2"]
        if expected is not None:
            argv += ["--expected-start-ticks", str(expected)]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        (directory / "command.json").write_text(json.dumps(argv, indent=2), encoding="utf-8")
        (directory / "stdout.txt").write_text(result.stdout, encoding="utf-8")
        (directory / "stderr.txt").write_text(result.stderr, encoding="utf-8")
        rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()] if rows_path.exists() else []
        return result, rows, directory

    def metric(rows):
        return next(row["instances"][0] for row in rows if row["event"] == "sample")

    def check(name, operation):
        try:
            details = operation()
            cases.append({"case": name, "passed": True, "details": details})
        except Exception as error:
            cases.append({"case": name, "passed": False, "error": str(error), "traceback": traceback.format_exc()})

    def healthy():
        with fixture(args.fixture, "healthy") as (process, ready):
            native_before = command(process, "hash")
            with VerifiedProcess(process.pid, base) as reader:
                pointer = reader.number(reader.module.baseaddress + base["poolPointerRva"], "Q")
                def digest():
                    return hashlib.sha256(reader.read(pointer, ready["capacity"] * 64)
                                          + reader.read(reader.module.baseaddress + base["poolPointerRva"], ready["stateSize"])).hexdigest()
                before = digest()
                result, rows, directory = capture(process, "healthy")
                after = digest()
            native_after = command(process, "hash")
            evidence = {"beforeSha256": before, "afterSha256": after,
                        "beforeNativeFnv64": native_before, "afterNativeFnv64": native_after}
            (directory / "memory-hashes.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            assert result.returncode == 0 and before == after and native_before == native_after
            item = metric(rows)
            assert item["capacity"] == 256 and item["usableCapacity"] == 255
            assert item["free"] == 252 and item["allocated"] == 3
            assert item["numericTypes"] == {"17": 1, "23": 2, "27": 252}
            assert item["reuseList"]["count"] == 252 and item["deferredCount"] == 2
            assert item["currentFunctionDepth"] == 3
            assert item["firstError"]["text"] == "owned fixture first error"
            assert item["firstError"]["status"] == "readable"
            assert rows[0]["accessMask"] == "0x1010" and rows[0]["gameValidation"] == "fixture-only"
            return evidence

    def identity():
        checks = []
        with fixture(args.fixture, "healthy") as (process, _):
            for name, change, expected, message in (
                ("wrong-hash", {"sha256": "0" * 64}, None, "executable hash differs"),
                ("wrong-build", {"timestamp": base["timestamp"] ^ 1}, None, "loaded module build differs"),
                ("wrong-start", {}, 0, "process start time differs"),
                ("disabled-profile", {"status": "disabled-private-offline-layout-only"}, None, "profile is disabled"),
                ("wrong-module", {"module": "different.exe"}, None, "executable name differs"),
            ):
                profile = copy.deepcopy(base)
                profile.update(change)
                result, rows, _ = capture(process, name, profile, expected)
                assert result.returncode != 0 and rows == [] and message in result.stderr, name
                checks.append(name)
        return checks

    def accepted_modes(modes):
        details = []
        for mode in modes:
            with fixture(args.fixture, mode) as (process, _):
                result, rows, _ = capture(process, mode)
                assert result.returncode == 0
                item = metric(rows)
                if mode == "uninitialized":
                    assert item["status"] == "uninitialized" and item["free"] is None and item["allocated"] is None
                elif mode == "unreadable-error":
                    assert item["free"] == 252 and item["firstError"]["status"] == "unreadable"
                elif mode == "truncated-error":
                    assert item["firstError"]["status"] == "truncated" and len(item["firstError"]["text"]) == 1024
                elif mode == "boundary-error":
                    assert item["firstError"]["status"] == "readable" and item["firstError"]["text"] == "owned fixture first error"
                details.append(item)
        return details

    def rejected_modes(modes):
        details = []
        for mode in modes:
            with fixture(args.fixture, mode) as (process, _):
                result, rows, _ = capture(process, mode)
                assert result.returncode == 0
                rejects = [row for row in rows if row["event"] == "rejected"]
                assert rejects and not any(row["event"] == "sample" for row in rows), mode
                details.append({"mode": mode, "error": rejects[0]["error"]})
        return details

    def recovery():
        with fixture(args.fixture, "exhausted") as (process, _):
            result, rows, _ = capture(process, "exhausted")
            exhausted = metric(rows)
            assert result.returncode == 0 and exhausted["free"] == 0 and exhausted["allocated"] == 255
            assert command(process, "recover") == "RECOVERED"
            result, rows, _ = capture(process, "recovered")
            recovered = metric(rows)
            assert result.returncode == 0 and recovered["free"] == 252 and recovered["allocated"] == 3
            return {"exhausted": exhausted, "recovered": recovered}

    def changing():
        with fixture(args.fixture, "changing") as (process, ready):
            profile = copy.deepcopy(base)
            profile["instances"][0]["capacity"] = ready["capacity"]
            result, rows, _ = capture(process, "changing", profile, duration=0.6)
            rejects = [row for row in rows if row["event"] == "rejected"]
            assert result.returncode == 0 and rejects
            assert all("changed" in row["error"] for row in rejects)
            return {"rejected": len(rejects), "accepted": sum(row["event"] == "sample" for row in rows)}

    def exited():
        with fixture(args.fixture, "exitsoon") as (process, _):
            result, rows, _ = capture(process, "exitsoon", duration=2)
            assert result.returncode == 0 and any(row["event"] == "process-exited" for row in rows)
            return [row["event"] for row in rows]

    check("healthy counts and unchanged native target", healthy)
    check("identity and disabled profile rejection", identity)
    check("uninitialized pool", lambda: accepted_modes(["uninitialized"]))
    check("missing and short pool bytes", lambda: rejected_modes(["missing", "short"]))
    check("reuse chain corruption and free-type disagreement", lambda: rejected_modes(["cycle", "out-of-range", "disagreement", "orphan-free"]))
    check("deferred chain corruption", lambda: rejected_modes(["deferred-cycle", "deferred-type", "deferred-range"]))
    check("exhaustion and native recovery", recovery)
    check("bounded error text", lambda: accepted_modes(["unreadable-error", "truncated-error", "boundary-error"]))
    check("changing read rejection", changing)
    check("process exit", exited)
    report = {"status": "passed" if all(case["passed"] for case in cases) else "failed", "cases": cases,
              "fixtureSha256": base["sha256"], "gameValidation": "unvalidated",
              "sourceSha256": {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
                  CLI, CLI.parent / "profile.py", CLI.parent / "snapshot.py", LIVE / "windows_process.py",
                  Path(__file__), Path(__file__).with_name("VmPoolFixture.cpp"), Path(__file__).with_name("Test-VmSampler.ps1"))},
              "consistency": "Repeated equal reads are not atomic snapshots."}
    (output / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "passed": sum(case["passed"] for case in cases), "total": len(cases), "report": str(output / "result.json")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
