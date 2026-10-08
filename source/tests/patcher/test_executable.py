"""Exercise the packaged CLI with owned unsupported-file fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    plan = json.loads(args.manifest.read_text())
    roots = {"workshop": args.output / "workshop", "game": args.output / "game"}
    targets = []
    for feature in plan["features"]:
        target = roots[feature["scope"]] / feature["relativePath"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(("Owned unsupported fixture for " + feature["id"]).encode())
        targets.append(target)
    for root in roots.values():
        root.mkdir(exist_ok=True)
    before = {str(path): sha(path) for path in targets}
    base = [str(args.executable.resolve())]
    flags = ["--workshop", str(roots["workshop"].resolve()), "--game", str(roots["game"].resolve()), "--state", str((args.output / "state").resolve())]
    commands = []
    for action in ("status", "apply"):
        result = subprocess.run(base + [action] + flags, capture_output=True, text=True, timeout=120)
        (args.output / (action + "-stdout.txt")).write_text(result.stdout, encoding="utf-8")
        (args.output / (action + "-stderr.txt")).write_text(result.stderr, encoding="utf-8")
        if action == "status":
            assert result.returncode == 0, result.stderr
            rows = json.loads(result.stdout)["result"]
            assert len(rows) == len(plan["features"])
            assert all(row["status"] == "unsupported" for row in rows)
        else:
            assert result.returncode == 1
            assert "unsupported hash" in result.stderr, result.stderr
        commands.append({"action": action, "exitCode": result.returncode})
    after = {str(path): sha(path) for path in targets}
    assert before == after
    report = {"status": "passed", "scope": "Packaged CLI with owned unsupported-file fixtures", "executableSha256": sha(args.executable), "manifestSha256": sha(args.manifest), "commands": commands, "targetHashesBefore": before, "targetHashesAfter": after, "gameplayValidated": False}
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
