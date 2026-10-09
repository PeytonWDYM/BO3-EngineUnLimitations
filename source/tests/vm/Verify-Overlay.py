"""Verify the monitor and rendered window against an owned native VM process."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

MODULE = importlib.util.spec_from_file_location("vm_e2e", Path(__file__).with_name("Verify-VmSampler.py"))
VM = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(VM)
REPO = Path(__file__).resolve().parents[3]
SHOW = REPO / "source/live/overlay/Show-Diagnostics.ps1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert REPO not in output.parents and output != REPO
    output.mkdir(parents=True, exist_ok=False)
    profile = VM.profile_for(args.fixture)
    cases = []
    for mode in ("healthy", "exhausted", "cycle", "uninitialized", "changing"):
        directory = output / mode
        directory.mkdir()
        with VM.fixture(args.fixture, mode) as (process, ready):
            selected = dict(profile, instances=[{"index": 0, "capacity": ready["capacity"]}])
            profile_file = directory / "profile.json"
            profile_file.write_text(json.dumps(selected))
            latest = directory / "latest.json"
            before = VM.command(process, "hash") if mode != "changing" else None
            argv = [sys.executable, str(VM.CLI), "--pid", str(process.pid), "--profile", str(profile_file),
                    "--output", str(directory / "rows.jsonl"), "--latest", str(latest), "--rate", "1",
                    "--duration", "5", "--attempts", "1"]
            monitor = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 10
                while not latest.exists() and monitor.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                proof = directory / "render"
                rendered = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
                                           "-File", str(SHOW), "-Latest", str(latest), "-ProofDirectory", str(proof),
                                           "-ExitAfterSeconds", "2"], capture_output=True, text=True, timeout=20,
                                          creationflags=subprocess.CREATE_NO_WINDOW)
                (directory / "overlay-stderr.txt").write_text(rendered.stderr)
                assert rendered.returncode == 0, rendered.stderr
                evidence = json.loads((proof / "render.json").read_text(encoding="utf-8-sig"))
                styles = evidence["ExtendedStyles"]
                assert styles & 0x08000000 and styles & 0x20 and styles & 0x80
                assert (proof / "overlay.png").stat().st_size > 1000
                stdout, stderr = monitor.communicate(timeout=15)
                assert monitor.returncode == 0, stderr.decode()
                final = json.loads(latest.read_text())
                assert final["event"] == "stopped"
                if before is not None:
                    assert VM.command(process, "hash") == before
                if mode == "cycle":
                    assert final["lastSample"] is None and final["rejected"] > 0
                    assert evidence["Status"] == "READ REJECTED"
                elif mode == "exhausted":
                    assert final["lastSample"][0]["free"] == 0 and "Free slots   : 0" in evidence["Text"]
                elif mode == "healthy":
                    assert final["lastSample"][0]["free"] == 252 and "Free slots   : 252" in evidence["Text"]
                elif mode == "uninitialized":
                    assert "no accepted initialized sample" in evidence["Text"]
                else:
                    assert final["rejected"] > 0
                # A second writer must fail without replacing the existing latest state.
                digest = hashlib.sha256(latest.read_bytes()).hexdigest()
                argv[argv.index("--output") + 1] = str(directory / "second.jsonl")
                second = subprocess.run(argv, capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                assert second.returncode != 0 and not (directory / "second.jsonl").exists()
                assert hashlib.sha256(latest.read_bytes()).hexdigest() == digest
                collision = directory / "collision.json"
                conflict = argv.copy()
                conflict[conflict.index("--latest") + 1] = str(collision)
                conflict[conflict.index("--output") + 1] = str(collision.with_suffix(".json.tmp"))
                blocked = subprocess.run(conflict, capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                assert blocked.returncode != 0 and b"temporary path" in blocked.stderr
                assert not collision.exists() and not collision.with_suffix(".json.tmp").exists()
                cases.append({"mode": mode, "passed": True, "render": str(proof / "overlay.png"), "styles": styles})
            finally:
                if monitor.poll() is None:
                    monitor.terminate()
                    monitor.communicate(timeout=10)
    report = {"status": "passed", "cases": cases, "gameValidation": "not established by this owned fixture",
              "sourceSha256": {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
                  VM.CLI, VM.CLI.parent / "latest_state.py", SHOW, SHOW.with_name("Overlay-Model.ps1"),
                  SHOW.with_name("OverlayWindow.cs"), Path(__file__))}}
    (output / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"status": "passed", "cases": len(cases), "report": str(output / "result.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
