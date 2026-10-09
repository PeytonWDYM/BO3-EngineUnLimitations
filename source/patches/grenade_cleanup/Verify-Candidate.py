"""Prepare, extract, and compare the private candidate through public tool CLIs."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], directory: Path, name: str) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=directory, capture_output=True, timeout=180)
    (directory / f"{name}.stdout.txt").write_bytes(result.stdout)
    (directory / f"{name}.stderr.txt").write_bytes(result.stderr)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--acts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lab = (Path.home() / ".codex/labs/bo3-engine").resolve(strict=True)
    output = args.output.resolve()
    if lab not in output.parents:
        parser.error("Keep test artifacts in the private BO3 lab.")
    output.mkdir(parents=True, exist_ok=False)
    source = args.source.resolve(strict=True)
    acts = args.acts.resolve(strict=True)
    before = digest(source)
    prepare = Path(__file__).with_name("Prepare-Candidate.py").resolve()
    candidate = output / "candidate"
    command = [sys.executable, str(prepare), "--source", str(source), "--output", str(candidate)]
    result = run(command, output, "prepare")
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    protected = digest(candidate / "core_mod.ff")
    assert run(command, output, "existing-output").returncode != 0
    assert digest(candidate / "core_mod.ff") == protected
    bad = output / "wrong-source.ff"
    bad.write_bytes(b"invalid")
    wrong = command.copy()
    wrong[wrong.index("--source") + 1] = str(bad)
    wrong[-1] = str(output / "rejected")
    assert run(wrong, output, "wrong-size").returncode != 0
    altered = bytearray(source.read_bytes())
    altered[-1] ^= 1
    bad.write_bytes(altered)
    assert run(wrong, output, "wrong-hash").returncode != 0
    assert not (output / "rejected").exists()
    original_extract = output / "original-extract"
    candidate_extract = output / "candidate-extract"
    inventory = []
    for directory, asset in ((original_extract, source), (candidate_extract, candidate / "core_mod.ff")):
        directory.mkdir()
        extracted = run([str(acts), "ffrbo3", str(asset)], directory, "extract")
        assert extracted.returncode == 0, extracted.stderr.decode(errors="replace")
        scripts = {str(path.relative_to(directory)): digest(path) for path in directory.rglob("*.gscc")}
        assert scripts, "The independent extractor produced no scripts."
        inventory.append(scripts)
    assert inventory[0].keys() == inventory[1].keys()
    changed = [name for name in inventory[0] if inventory[0][name] != inventory[1][name]]
    assert len(changed) == 1 and changed[0].endswith("scripts\\zm\\_zm_weapons.gscc"), changed
    script = candidate_extract / changed[0]
    decompiled = output / "decompiled"
    result = run([str(acts), "gscd", "-g", "-a", "-H", "-L", "-o", str(decompiled), str(script)], output, "decompile")
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert digest(source) == before
    verification = json.loads((candidate / "verification.json").read_text())
    report = {"status": "passed", "scope": "Offline extraction and preparation only. No game or co-op validation.",
              "scriptCount": len(inventory[0]), "changedScripts": changed, "sourceUnchanged": True,
              "existingOutputPreserved": True, "wrongSizeRejected": True, "wrongHashRejected": True,
              "actsSha256": digest(acts), "verification": verification}
    (output / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
