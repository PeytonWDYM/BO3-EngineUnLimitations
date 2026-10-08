"""Exercise release unpacking and guard construction on private owned inputs."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from patchplans.native import ORIGINAL_SHA256, PATCHED_SHA256, transform


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--upx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    repo = Path(__file__).resolve().parents[3]
    if output == repo or repo in output.parents or output.exists():
        parser.error("Use a new private evidence directory outside the repository.")
    source = args.original.read_bytes()
    if hashlib.sha256(source).hexdigest() != ORIGINAL_SHA256:
        parser.error("Use the exact original native module.")
    output.mkdir(parents=True)
    resources = output / "resources"
    (resources / "upx").mkdir(parents=True)
    (resources / "patchplans").mkdir()
    shutil.copyfile(args.upx, resources / "upx" / "upx.exe")
    shutil.copyfile(repo / "source" / "patchplans" / "native_profile.json", resources / "patchplans" / "native_profile.json")
    candidate = transform(source, resources)
    assert hashlib.sha256(candidate).hexdigest() == PATCHED_SHA256
    (output / "T7Overcharged.ff").write_bytes(candidate)
    try:
        transform(source + b"changed", resources)
    except ValueError:
        pass
    else:
        raise AssertionError("A changed native input was accepted.")
    (resources / "upx" / "upx.exe").write_bytes(b"changed tool")
    try:
        transform(source, resources)
    except ValueError:
        pass
    else:
        raise AssertionError("An altered tool was executed.")
    assert hashlib.sha256(args.original.read_bytes()).hexdigest() == ORIGINAL_SHA256
    report = {"passed": True, "candidateSha256": PATCHED_SHA256,
              "sourcePreserved": True, "changedInputRefused": True,
              "changedToolRefused": True, "moduleExecuted": False,
              "gameValidated": False}
    (output / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
