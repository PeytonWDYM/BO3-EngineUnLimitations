"""Verify snapshot diagnostics with real native pool states captured in one dump."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from minidump.minidumpfile import MinidumpFile
import pefile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", required=True, type=Path)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    cli = repo / "source/reverse/Read-EntitySnapshot.py"
    pe = pefile.PE(str(args.fixture))
    exports = {item.name.decode(): item.address for item in pe.DIRECTORY_ENTRY_EXPORT.symbols}
    dump = MinidumpFile.parse(str(args.dump))
    module = next(item for item in dump.modules.modules if item.name.endswith(args.fixture.name))
    identity_path = args.output / "identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8-sig"))
    identity["modules"] = [{"name": args.fixture.name, "baseAddress": hex(module.baseaddress), "size": module.size}]
    identity_path.write_text(json.dumps(identity), encoding="utf-8")
    checks = []
    scenarios = {
        "Healthy": {"status": "initialized", "normalActive": 10, "cleanupFlaggedActive": 6, "cleanupFlaggedPastDelay": 6, "freeListCount": 0, "sentinelActive": 1, "fakeActive": 1},
        "MixedCleanupClock": {"status": "initialized", "normalActive": 10, "cleanupFlaggedActive": 4,
                              "cleanupFlaggedPastDelay": 2, "cleanupFlaggedOldestClockAgeMs": 500,
                              "cleanupFlaggedNumericTypes": {"4": 2, "102": 2},
                              "numericTypes": {"1": 4, "4": 4, "102": 2}},
        "Exhausted": {"status": "initialized", "normalActive": 24, "failureCondition": True},
        "Recovered": {"status": "initialized", "normalActive": 4, "freeListCount": 20, "failureCondition": False, "headReusable": True},
        "Uninitialized": {"status": "uninitialized"},
        "Cyclic": "cycle",
        "InvalidFlag": "in-use",
        "InvalidPointer": "active slot",
        "MissingMemory": "not captured",
    }
    digest = hashlib.sha256(args.fixture.read_bytes()).hexdigest()
    profile = {
        "module": args.fixture.name, "sha256": digest,
        "imageSize": pe.OPTIONAL_HEADER.SizeOfImage, "timestamp": pe.FILE_HEADER.TimeDateStamp,
        "layout": {"stride": 16, "capacity": 32, "normalLimit": 24, "reservedCount": 4, "fakeStart": 26,
                   "inUseOffset": 0, "temporaryOffset": 1, "temporaryFormat": "B", "typeOffset": 2,
                   "freeTimeOffset": 4, "freeNextOffset": 8, "reuseDelayMs": 500, "temporaryCleanupDelayMs": 300},
    }
    for name, expected in scenarios.items():
        rva = exports[name]
        profile["globals"] = {"pool": rva, "highWater": rva + 8, "time": rva + 12, "head": rva + 16, "tail": rva + 24}
        profile_path = args.output / (name + "-profile.json")
        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        report_path = args.output / (name + "-report.json")
        command = [sys.executable, str(cli), str(args.dump), "--profile", str(profile_path),
                   "--identity", str(identity_path), "--output", str(report_path)]
        result = subprocess.run(command, capture_output=True, text=True)
        if isinstance(expected, dict):
            assert result.returncode == 0, result.stderr
            report = json.loads(report_path.read_text())
            for key, value in expected.items():
                assert report[key] == value, (name, key, report)
            assert not any(key.startswith("temporary") for key in report), report
            if name == "Uninitialized":
                assert "normalActive" not in report
        else:
            assert result.returncode != 0 and expected in result.stderr, (name, result.stderr)
            assert not report_path.exists()
        checks.append(name)
    profile["sha256"] = "0" * 64
    bad = args.output / "wrong-build.json"
    bad.write_text(json.dumps(profile), encoding="utf-8")
    wrong_output = args.output / "wrong-build-report.json"
    result = subprocess.run([sys.executable, str(cli), str(args.dump), "--profile", str(bad),
                             "--identity", str(identity_path), "--output", str(wrong_output)], capture_output=True, text=True)
    assert result.returncode != 0 and "hash" in result.stderr and not wrong_output.exists()
    checks.append("Wrong build")
    (args.output / "report.json").write_text(json.dumps({"passed": True, "checks": checks, "dump": str(args.dump)}, indent=2), encoding="utf-8")
    print("PASS: " + str(args.output))


if __name__ == "__main__":
    main()
