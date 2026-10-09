"""Check optional frozen payload bytes and refusal with inert owned game files."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from PyInstaller.archive.readers import CArchiveReader


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bundled", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    archive = CArchiveReader(str(args.executable))
    entries = {name.replace("\\", "/"): name for name in archive.toc}
    expected = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    enhanced = {name for name in entries if name.startswith("enhanced/")}
    hashes = {}
    if args.bundled:
        assert enhanced == {"enhanced/manifest.json", *("enhanced/" + name for name in expected["files"])}
        embedded = archive.extract(entries["enhanced/manifest.json"])
        assert embedded == args.manifest.read_bytes()
        for name, digest in expected["files"].items():
            hashes[name] = sha(archive.extract(entries["enhanced/" + name]))
            assert hashes[name] == digest
    else:
        assert not enhanced
    game = args.output / "owned-game"
    game.mkdir()
    (game / "BlackOps3.exe").write_bytes(b"Owned unsupported executable, never executed")
    (game / "settings.ini").write_bytes(b"Owned settings must stay unchanged")
    before = {p.name: sha(p.read_bytes()) for p in game.iterdir()}
    child = subprocess.run([str(args.executable.resolve()), "play-enhanced", "--game", str(game.resolve())],
                           capture_output=True, text=True, timeout=120)
    (args.output / "stderr.txt").write_text(child.stderr, encoding="utf-8")
    assert child.returncode == 1, child.stdout
    assert ("unsupported" if args.bundled else "not bundled") in child.stderr, child.stderr
    after = {p.name: sha(p.read_bytes()) for p in game.iterdir()}
    assert before == after
    report = {"status": "passed", "bundled": args.bundled, "payloadSha256": hashes,
              "artifactSha256": sha(args.executable.read_bytes()), "targetHashesBefore": before,
              "targetHashesAfter": after, "nativePayloadExecuted": False, "gameplayValidated": False}
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
