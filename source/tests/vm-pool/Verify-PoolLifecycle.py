"""Exercise the lifecycle CLI against owned Windows processes and retain receipts."""

import argparse
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

import pefile

REPO = Path(__file__).resolve().parents[3]
CLI = REPO / "source/live/pool_lifecycle.py"
API = REPO / "source/live/windows_process.py"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def fixture(executable, mode):
    child = subprocess.Popen([str(executable), mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        ready = json.loads(child.stdout.readline())
        assert ready["pid"] == child.pid
        yield child, ready
    finally:
        if child.poll() is None:
            child.stdin.write("stop\n")
            child.stdin.flush()
        child.communicate(timeout=10)
        assert child.returncode == 0


def command(child, text):
    child.stdin.write(text + "\n")
    child.stdin.flush()
    return child.stdout.readline().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert output != REPO and REPO not in output.parents
    pe = pefile.PE(str(args.fixture))
    exports = {item.name: item.address for item in pe.DIRECTORY_ENTRY_EXPORT.symbols}
    state = exports[b"lifecycleState"]
    guard = exports[b"lifecycleFixtureGuard"]
    base = {
        "schemaVersion": 1, "status": "fixture-only", "module": args.fixture.name,
        "sha256": digest(args.fixture), "imageSize": pe.OPTIONAL_HEADER.SizeOfImage,
        "timestamp": pe.FILE_HEADER.TimeDateStamp, "poolPointerRva": state,
        "serverTimeRva": state + 8, "entityPoolPointerRva": state + 16,
        "arenaRecordRva": state + 24, "poolAllocationBytes": 128,
        "readerSourceSha256": digest(CLI) if CLI.exists() else "0" * 64,
        "processApiSourceSha256": digest(API),
        "codeEvidence": [{"startRva": guard, "endRva": guard + 8,
                          "sha256": hashlib.sha256(pe.get_data(guard, 8)).hexdigest()}],
    }
    cases = []
    sequence = 0

    def prepare(child, ready, name, edits=None):
        nonlocal sequence
        sequence += 1
        directory = output / f"{sequence:02d}-{name}"
        directory.mkdir()
        profile = copy.deepcopy(base)
        profile.update(expectedProcessId=child.pid, expectedProcessStartTicks=ready["startTicks"])
        profile.update(edits or {})
        profile_path = directory / "profile.json"
        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        rows_path = directory / "samples.jsonl"
        argv = [sys.executable, str(CLI), "--pid", str(child.pid), "--profile", str(profile_path),
                "--output", str(rows_path), "--duration", "0.15"]
        (directory / "command.json").write_text(json.dumps(argv, indent=2))
        return directory, rows_path, argv

    def read_rows(path):
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def capture(child, ready, name, edits=None, duration="0.15"):
        directory, rows_path, argv = prepare(child, ready, name, edits)
        argv[-1] = duration
        (directory / "command.json").write_text(json.dumps(argv, indent=2))
        result = subprocess.run(argv, capture_output=True, text=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        (directory / "stdout.txt").write_text(result.stdout)
        (directory / "stderr.txt").write_text(result.stderr)
        return result, read_rows(rows_path), directory

    def check(name, operation):
        try:
            cases.append({"case": name, "passed": True, "details": operation()})
        except Exception as error:
            cases.append({"case": name, "passed": False, "error": str(error), "traceback": traceback.format_exc()})

    def healthy():
        with fixture(args.fixture, "healthy") as (child, ready):
            before = command(child, "hash")
            result, rows, directory = capture(child, ready, "healthy")
            after = command(child, "hash")
            assert result.returncode == 0 and before == after
            samples = [row for row in rows if row["event"] == "sample"]
            assert len(samples) == 1
            data = samples[0]["metadata"]
            assert data["serverTime"] == 1000 and data["arena"]["cursor"] == 0x10000
            assert data["arena"]["size"] == 0x200000
            assert [mark["name"] for mark in data["arena"]["marks"]] == ["$init", "Level"]
            assert data["serverPoolOffset"] == 0x3000
            assert rows[0]["accessMask"] == "0x1010" and rows[0]["rateHz"] == 1
            receipt = {"beforeNativeFnv64": before, "afterNativeFnv64": after,
                       "poolAndEntityMemory": "Reserved PAGE_NOACCESS. Successful reads prove metadata-only access."}
            (directory / "memory-receipt.json").write_text(json.dumps(receipt, indent=2))
            return receipt

    def admission():
        results = []
        with fixture(args.fixture, "healthy") as (child, ready):
            mutations = [
                ("hash", {"sha256": "0" * 64}),
                ("timestamp", {"timestamp": base["timestamp"] ^ 1}),
                ("module", {"module": "wrong.exe"}),
                ("pid", {"expectedProcessId": child.pid + 1}),
                ("ticks", {"expectedProcessStartTicks": ready["startTicks"] + 1}),
                ("disabled", {"status": "disabled"}),
                ("no-code", {"codeEvidence": []}),
                ("bad-code", {"codeEvidence": [{"startRva": guard, "endRva": guard + 8, "sha256": "0" * 64}]}),
                ("reader-source", {"readerSourceSha256": "0" * 64}),
                ("global-range", {"arenaRecordRva": base["imageSize"] - 8}),
            ]
            for name, edits in mutations:
                result, rows, _ = capture(child, ready, name, edits)
                assert result.returncode == 2 and not rows and "Pool lifecycle:" in result.stderr, name
                results.append(name)
        return results

    def layouts():
        results = []
        for mode in ["bad-descriptor", "bad-name", "long-name", "mark-count", "cursor-overflow", "pool-outside", "descending-marks"]:
            with fixture(args.fixture, mode) as (child, ready):
                result, rows, _ = capture(child, ready, mode)
                rejects = [row for row in rows if row["event"] == "rejected"]
                assert result.returncode == 0 and rejects and not any(row["event"] == "sample" for row in rows), mode
                results.append({"mode": mode, "error": rejects[0]["error"]})
        return results

    def uninitialized():
        with fixture(args.fixture, "uninitialized") as (child, ready):
            result, rows, _ = capture(child, ready, "uninitialized")
            assert result.returncode == 0
            data = next(row["metadata"] for row in rows if row["event"] == "sample")
            assert data["arena"] is None and data["serverPoolPointer"] == "0x0"
            return data

    def changing():
        with fixture(args.fixture, "changing") as (child, ready):
            result, rows, _ = capture(child, ready, "changing", duration="2.2")
            rejects = [row for row in rows if row["event"] == "rejected"]
            assert result.returncode == 0 and rejects
            assert all("changed" in row["error"] for row in rejects)
            return {"rejections": len(rejects)}

    def transitions(mode):
        with fixture(args.fixture, "healthy") as (child, ready):
            directory, path, argv = prepare(child, ready, mode)
            argv[-1] = "2.3"
            (directory / "command.json").write_text(json.dumps(argv, indent=2))
            sampler = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if any(row["event"] == "sample" for row in read_rows(path)):
                        break
                    if sampler.poll() is not None:
                        raise AssertionError("Sampler exited before first sample.")
                    time.sleep(0.02)
                else:
                    raise AssertionError("Sampler did not publish its first sample.")
                assert command(child, mode) == ("REPLACED" if mode == "replace" else "RETAINED")
                stdout, stderr = sampler.communicate(timeout=10)
                (directory / "stdout.txt").write_text(stdout)
                (directory / "stderr.txt").write_text(stderr)
                assert sampler.returncode == 0
            finally:
                if sampler.poll() is None:
                    sampler.terminate()
                    sampler.communicate(timeout=5)
            rows = read_rows(path)
            samples = [row for row in rows if row["event"] == "sample"]
            changed = next(row for row in samples if row["changes"])
            assert "serverTimeDecreased" in changed["changes"]
            assert ("serverPoolPointerChanged" in changed["changes"]) == (mode == "replace")
            if mode == "replace":
                assert "arenaMarksChanged" in changed["changes"]
                assert "entityPoolPointerChanged" in changed["changes"]
            return changed["changes"]

    def exited():
        with fixture(args.fixture, "exitsoon") as (child, ready):
            result, rows, _ = capture(child, ready, "exitsoon", duration="2.5")
            assert result.returncode == 0 and any(row["event"] == "process-exited" for row in rows)
            return [row["event"] for row in rows]

    def output_guards():
        with fixture(args.fixture, "healthy") as (child, ready):
            directory, path, argv = prepare(child, ready, "existing-output")
            path.write_text("KEEP")
            result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
            assert result.returncode == 2 and path.read_text() == "KEEP"
            argv[argv.index("--output") + 1] = str(REPO / "forbidden-lifecycle-output.jsonl")
            result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
            assert result.returncode == 2 and "outside the repository" in result.stderr
            junction = directory / "repo-junction"
            link = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(REPO)], capture_output=True, text=True)
            assert link.returncode == 0, link.stderr
            argv[argv.index("--output") + 1] = str(junction / "forbidden-lifecycle-output.jsonl")
            result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
            assert result.returncode == 2 and "outside the repository" in result.stderr
            return ["existing-output", "repository-output", "junction-to-repository-output"]

    check("healthy metadata and unchanged native memory", healthy)
    check("identity, source, and mapped-code admission", admission)
    check("malformed metadata rejection", layouts)
    check("uninitialized metadata", uninitialized)
    check("changing marks rejected", changing)
    check("pool replacement observed", lambda: transitions("replace"))
    check("time reset with retained pool", lambda: transitions("retain"))
    check("process exit", exited)
    check("output guards", output_guards)
    sources = [CLI, API, Path(__file__), Path(__file__).with_name("LifecycleFixture.cpp"),
               Path(__file__).with_name("Test-PoolLifecycle.ps1"), Path(__file__).with_name("failure-cases.txt")]
    report = {"status": "passed" if all(case["passed"] for case in cases) else "failed", "cases": cases,
              "fixtureSha256": digest(args.fixture), "sourceSha256": {str(p.relative_to(REPO)): digest(p) for p in sources if p.exists()},
              "scope": "Owned Windows process only. No BO3 attachment. Equal repeated reads are not an atomic snapshot."}
    (output / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"status": report["status"], "passed": sum(case["passed"] for case in cases),
                      "total": len(cases), "report": str(output / "result.json")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
