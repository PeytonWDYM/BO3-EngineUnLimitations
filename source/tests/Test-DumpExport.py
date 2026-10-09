"""Verify dump export against a real fixture snapshot and its original executable."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pefile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", required=True, type=Path)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("Write the E2E artifact outside the repository.")
    output.mkdir(parents=True, exist_ok=False)
    cli = repo / "source" / "reverse" / "Export-DumpModule.py"
    export = output / "module"
    command = [sys.executable, str(cli), str(args.dump), "--module", args.fixture.name]
    before = hashlib.file_digest(args.dump.open("rb"), "sha256").hexdigest()
    subprocess.run(command + ["--output", str(export)], check=True, capture_output=True, text=True)
    report = json.loads((export / "module.json").read_text())
    original = pefile.PE(str(args.fixture), fast_load=True)
    assert report["peHeaders"] == "captured"
    assert report["imageSize"] == original.OPTIONAL_HEADER.SizeOfImage
    assert report["timestamp"] == original.FILE_HEADER.TimeDateStamp
    assert report["sections"] and all(section["complete"] for section in report["sections"])
    checks = [
        "Exports real fixture memory with complete PE section coverage.",
        "Matches the original executable image size and timestamp.",
    ]
    rejected = repo / "research" / "captures" / ("rejected-" + uuid.uuid4().hex)
    for description, destination, selected in (
        ("repository destination", rejected, args.fixture.name),
        ("existing destination", export, args.fixture.name),
        ("missing module", output / "missing", "missing-module.exe"),
    ):
        result = subprocess.run([
            sys.executable, str(cli), str(args.dump), "--module", selected,
            "--output", str(destination),
        ], capture_output=True, text=True)
        assert result.returncode != 0, description
        if description != "existing destination":
            assert not destination.exists(), description
        checks.append("Rejects " + description + ".")
    after = hashlib.file_digest(args.dump.open("rb"), "sha256").hexdigest()
    assert before == after
    checks.append("Preserves the input dump hash.")
    artifact = {"passed": True, "checks": checks, "dump": str(args.dump), "export": str(export)}
    (output / "report.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps(artifact, indent=2))


if __name__ == "__main__":
    main()
