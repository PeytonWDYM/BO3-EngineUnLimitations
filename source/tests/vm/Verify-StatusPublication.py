"""Hold real Windows file locks while the CLI samples an owned native process.

Failures to cover before implementation: a locked destination must not stop the
JSONL capture, a locked temporary file must recover after release, and a lock
held through shutdown must leave valid status JSON and a complete sample log.
"""

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

MODULE = importlib.util.spec_from_file_location("vm_e2e", Path(__file__).with_name("Verify-VmSampler.py"))
VM = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(VM)
KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)
KERNEL.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
KERNEL.CreateFileW.restype = wintypes.HANDLE
KERNEL.CloseHandle.argtypes = [wintypes.HANDLE]
KERNEL.CloseHandle.restype = wintypes.BOOL


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def wait_for(check, monitor):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if check():
            return
        assert monitor.poll() is None, "The sampler stopped before the expected state."
        time.sleep(0.02)
    raise AssertionError("The expected state did not arrive.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert output != VM.REPO and VM.REPO not in output.parents
    output.mkdir(parents=True, exist_ok=False)
    cases = []
    for name, temporary, release in (("destination-recovery", False, True),
                                     ("temporary-recovery", True, True),
                                     ("locked-through-stop", False, False)):
        directory = output / name
        directory.mkdir()
        handle = None
        monitor = None
        try:
            with VM.fixture(args.fixture, "healthy") as (target, ready):
                before = VM.command(target, "hash")
                profile = directory / "profile.json"
                profile.write_text(json.dumps(VM.profile_for(args.fixture)))
                latest = directory / "latest.json"
                capture = directory / "rows.jsonl"
                argv = [sys.executable, str(VM.CLI), "--pid", str(target.pid), "--profile", str(profile),
                        "--output", str(capture), "--latest", str(latest), "--duration", "2.5", "--rate", "10"]
                (directory / "command.json").write_text(json.dumps(argv, indent=2))
                monitor = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                wait_for(lambda: capture.exists() and latest.exists()
                         and json.loads(latest.read_text()).get("lastSample") is not None, monitor)
                locked = latest.with_suffix(".json.tmp") if temporary else latest
                # Share reads and writes, but deny deletion and atomic replacement.
                handle = KERNEL.CreateFileW(str(locked), 0x80000000, 3, None, 4, 0x80, None)
                if handle == ctypes.c_void_p(-1).value:
                    handle = None
                    raise ctypes.WinError(ctypes.get_last_error())
                old_status = latest.read_bytes()
                before_count = sum(row["event"] == "sample" for row in rows(capture))
                wait_for(lambda: any(row["event"] == "overlay-publication-failed" for row in rows(capture)), monitor)
                wait_for(lambda: sum(row["event"] == "sample" for row in rows(capture)) >= before_count + 3, monitor)
                assert latest.read_bytes() == old_status
                assert json.loads(old_status)["lastSample"][0]["free"] == 252
                if release:
                    assert KERNEL.CloseHandle(handle)
                    handle = None
                    wait_for(lambda: latest.read_bytes() != old_status, monitor)
                stdout, stderr = monitor.communicate(timeout=10)
                (directory / "stdout.txt").write_bytes(stdout)
                (directory / "stderr.txt").write_bytes(stderr)
                captured = rows(capture)
                failures = [row for row in captured if row["event"] == "overlay-publication-failed"]
                assert monitor.returncode == 0, stderr.decode()
                assert captured[-1]["event"] in ("stopped", "overlay-publication-failed")
                stopped = next(row for row in captured if row["event"] == "stopped")
                assert stopped["accepted"] >= before_count + 3
                assert failures and all(row["winError"] in (5, 32, 33) for row in failures)
                assert b"overlay" in stderr.lower()
                final = json.loads(latest.read_text())
                if release:
                    assert final["event"] == "stopped"
                else:
                    assert latest.read_bytes() == old_status
                assert VM.command(target, "hash") == before
                cases.append({"case": name, "passed": True, "fixturePid": target.pid,
                              "fixtureReady": ready, "accepted": stopped["accepted"],
                              "publicationFailures": len(failures), "nativeChecksum": before})
        except Exception as error:
            cases.append({"case": name, "passed": False, "error": str(error), "traceback": traceback.format_exc()})
        finally:
            if handle is not None:
                assert KERNEL.CloseHandle(handle)
            if monitor is not None:
                if monitor.poll() is None:
                    monitor.terminate()
                stdout, stderr = monitor.communicate(timeout=10)
                (directory / "stdout.txt").write_bytes(stdout)
                (directory / "stderr.txt").write_bytes(stderr)
    report = {"passed": all(case["passed"] for case in cases), "cases": cases,
              "scope": "Real Windows sharing locks and the full CLI against an owned native process.",
              "sourceSha256": {str(path.relative_to(VM.REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in (Path(__file__), VM.CLI, VM.CLI.with_name("latest_state.py"))}}
    (output / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"passed": report["passed"], "report": str(output / "result.json")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
