"""Verify the live sampler against an independent native process and save evidence."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dynamic-fixture", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("Write test evidence outside the repository.")
    output.mkdir(parents=True, exist_ok=False)
    cli = repo / "source/live/Read-LiveEntities.py"
    checks = []
    fixture_digest = hashlib.sha256(args.fixture.read_bytes()).hexdigest()
    target = subprocess.Popen([str(args.fixture)], creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        time.sleep(0.3)
        scenarios = {
            "Healthy": {"normalActive": 10, "reservedActive": 4, "allocatableActive": 6,
                        "sentinelActive": 1, "fakeActive": 1, "temporaryPastCleanupDelay": 6},
            "Exhausted": {"normalActive": 24, "freeListCount": 0, "failureCondition": True},
            "Recovered": {"normalActive": 4, "freeListCount": 20, "headReusable": True, "failureCondition": False},
            "Uninitialized": {"status": "uninitialized"},
            "Cyclic": "cycle", "InvalidFlag": "in-use", "InvalidPointer": "active slot", "MissingMemory": "ReadProcessMemory",
        }
        for name, expected in scenarios.items():
            capture = output / (name + ".jsonl")
            command = [sys.executable, str(cli), "--pid", str(target.pid), "--profile",
                       str(args.profiles / (name + "-profile.json")), "--output", str(capture),
                       "--duration", "0.5", "--rate", "10"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
            (output / (name + ".stderr.txt")).write_text(result.stderr, encoding="utf-8")
            assert result.returncode == 0, (name, result.stderr)
            rows = [json.loads(line) for line in capture.read_text().splitlines()]
            samples = [row for row in rows if row["event"] == "sample"]
            rejected = [row for row in rows if row["event"] == "rejected"]
            if isinstance(expected, dict):
                assert len(samples) >= 3 and not rejected, (name, rows)
                for sample in samples:
                    for key, value in expected.items():
                        assert sample["pool"][key] == value, (name, key, sample)
                if name == "Healthy":
                    assert samples[-1]["maxNormalActive"] == 10
                    assert samples[-1]["pool"]["numericTypes"] == {"1": 4, "25": 6}
            else:
                assert not samples and rejected, (name, rows)
                assert all(expected in row["reason"] for row in rejected), (name, rows)
            assert rows[0]["accessMask"] == 0x1010
            assert rows[-1]["event"] == "stopped"
            sequence = [row["sequence"] for row in rows if "sequence" in row]
            assert sequence == list(range(len(sequence))), sequence
            checks.append(name)

        profile = json.loads((args.profiles / "Healthy-profile.json").read_text(encoding="utf-8-sig"))
        for name, field, value, message in (
            ("WrongHash", "sha256", "0" * 64, "hash"),
            ("WrongSize", "imageSize", profile["imageSize"] + 4096, "module build"),
            ("WrongTimestamp", "timestamp", 0, "module build"),
        ):
            invalid = dict(profile, **{field: value})
            path = output / (name + "-profile.json")
            path.write_text(json.dumps(invalid), encoding="utf-8")
            capture = output / (name + ".jsonl")
            result = subprocess.run([sys.executable, str(cli), "--pid", str(target.pid), "--profile", str(path),
                                     "--output", str(capture), "--duration", "0.1"], capture_output=True, text=True, timeout=20)
            assert result.returncode != 0 and message in result.stderr and not capture.exists(), (name, result.stderr)
            checks.append(name)

        # Read the same native state before and after a CLI run to detect target writes.
        sys.path.insert(0, str(repo / "source/live"))
        from windows_process import LiveProcess
        with LiveProcess(target.pid, profile) as memory:
            addresses = memory.pool_ranges(profile)
            before = [memory.read(address, size) for address, size in addresses]
            capture = output / "NoWrites.jsonl"
            result = subprocess.run([sys.executable, str(cli), "--pid", str(target.pid), "--profile",
                                     str(args.profiles / "Healthy-profile.json"), "--output", str(capture),
                                     "--duration", "0.5"], capture_output=True, text=True, timeout=20)
            assert result.returncode == 0, result.stderr
            assert before == [memory.read(address, size) for address, size in addresses]
            expected_start = str(memory.started_ticks + 1)
        checks.append("No target writes")
        capture = output / "WrongStart.jsonl"
        result = subprocess.run([sys.executable, str(cli), "--pid", str(target.pid), "--profile",
                                 str(args.profiles / "Healthy-profile.json"), "--output", str(capture),
                                 "--expected-start-ticks", expected_start], capture_output=True, text=True, timeout=20)
        assert result.returncode != 0 and "process start" in result.stderr and not capture.exists()
        checks.append("Wrong process start")
        for name, arguments, message in (
            ("RepositoryOutput", ["--output", str(repo / "forbidden-live-capture.jsonl")], "outside the repository"),
            ("ExistingOutput", ["--output", str(output / "Healthy.jsonl")], "new report path"),
            ("InvalidRate", ["--rate", "0"], "rate"),
            ("InvalidDuration", ["--duration", "-1"], "duration"),
            ("InvalidAttempts", ["--attempts", "0"], "attempts"),
        ):
            capture = output / (name + ".jsonl")
            result = subprocess.run([sys.executable, str(cli), "--pid", str(target.pid), "--profile",
                                     str(args.profiles / "Healthy-profile.json"), "--output", str(capture),
                                     *arguments], capture_output=True, text=True, timeout=20)
            assert result.returncode != 0 and message in result.stderr and not capture.exists(), (name, result.stderr)
            checks.append(name)
        oversized = dict(profile, layout=dict(profile["layout"], stride=65536, capacity=65536))
        oversized_path = output / "Oversized-profile.json"
        oversized_path.write_text(json.dumps(oversized), encoding="utf-8")
        capture = output / "Oversized.jsonl"
        result = subprocess.run([sys.executable, str(cli), "--pid", str(target.pid), "--profile",
                                 str(oversized_path), "--output", str(capture)], capture_output=True, text=True, timeout=20)
        assert result.returncode != 0 and "pool size" in result.stderr and not capture.exists()
        checks.append("Oversized pool")
        capture = output / "Exited.jsonl"
        sampler = subprocess.Popen([sys.executable, str(cli), "--pid", str(target.pid), "--profile",
                                    str(args.profiles / "Healthy-profile.json"), "--output", str(capture), "--duration", "10"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 10
        while (not capture.exists() or capture.stat().st_size == 0) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert capture.exists(), "The sampler did not attach."
        time.sleep(0.2)
        target.terminate()
        target.wait(timeout=10)
        stdout, stderr = sampler.communicate(timeout=10)
        assert sampler.returncode == 0, stderr
        rows = [json.loads(line) for line in capture.read_text().splitlines()]
        assert any(row["event"] == "process_exit" for row in rows), rows
        checks.append("Process exit")
        assert hashlib.sha256(args.fixture.read_bytes()).hexdigest() == fixture_digest
        if args.dynamic_fixture:
            import pefile
            with pefile.PE(str(args.dynamic_fixture)) as pe:
                rva = next(item.address for item in pe.DIRECTORY_ENTRY_EXPORT.symbols if item.name == b"Moving")
                moving_profile = dict(profile, module=args.dynamic_fixture.name,
                                      sha256=hashlib.sha256(args.dynamic_fixture.read_bytes()).hexdigest(),
                                      imageSize=pe.OPTIONAL_HEADER.SizeOfImage, timestamp=pe.FILE_HEADER.TimeDateStamp,
                                      layout=dict(profile["layout"], stride=1024, capacity=8192),
                                      globals={"pool": rva, "highWater": rva + 8, "time": rva + 12,
                                               "head": rva + 16, "tail": rva + 24})
            path = output / "Moving-profile.json"
            path.write_text(json.dumps(moving_profile), encoding="utf-8")
            moving = subprocess.Popen([str(args.dynamic_fixture)], creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                time.sleep(0.1)
                capture = output / "Moving.jsonl"
                result = subprocess.run([sys.executable, str(cli), "--pid", str(moving.pid), "--profile", str(path),
                                         "--output", str(capture), "--duration", "0.8", "--rate", "5", "--attempts", "2"],
                                        capture_output=True, text=True, timeout=20)
                assert result.returncode == 0, result.stderr
                rows = [json.loads(line) for line in capture.read_text().splitlines()]
                rejects = [row for row in rows if row["event"] == "rejected"]
                assert rejects and all(row["attempts"] == 2 and "changed" in row["reason"] for row in rejects), rows
                assert all("pool" not in row for row in rejects)
                checks.append("Observed native metadata changes and bounded retries")
            finally:
                moving.terminate()
                moving.wait(timeout=10)
        report = {"passed": True, "checks": checks, "fixture": str(args.fixture.resolve()),
                  "sha256": fixture_digest, "evidence": str(output), "accessMask": "0x1010",
                  "limits": "Stable native states verify counts and read-only access. They do not prove atomic game reads."}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        if target.poll() is None:
            target.terminate()
            target.wait(timeout=10)


if __name__ == "__main__":
    main()
