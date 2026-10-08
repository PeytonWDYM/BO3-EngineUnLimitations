"""Apply and remove the frozen patcher over private copies of exact owned assets."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("artifact", "stock-core", "stock-native", "stock-storm", "legacy-core", "guard-native", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--stock-spawn", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    output = args.output.resolve()
    if output.exists() or output == repo or repo in output.parents:
        parser.error("Select a new private evidence directory outside the repository.")
    manifest_path = repo / "source" / "patchplans" / "release.json"
    manifest = json.loads(manifest_path.read_text())
    build = json.loads((args.artifact.parent / "build.json").read_text())
    if digest(args.artifact) != build["artifactSha256"] or digest(manifest_path) != build["manifestSha256"]:
        parser.error("The packaged executable or current manifest differs from the build record.")
    inputs = {"aae-core": args.stock_core, "aae-native": args.stock_native, "storm-bow": args.stock_storm}
    if args.stock_spawn is not None:
        inputs["zero-spawn-delay"] = args.stock_spawn
    features = {row["id"]: row for row in manifest["features"]}
    enabled = {identity for identity, row in features.items() if row.get("applyAvailability", "enabled") == "enabled"}
    retired = set(features) - enabled
    if set(inputs) != set(features):
        parser.error("Supply an original input for every file in the current test manifest.")
    for identity, path in inputs.items():
        if digest(path) != features[identity]["originalSha256"]:
            parser.error(f"The original {identity} has an unsupported hash.")
    if digest(args.legacy_core) not in features["aae-core"]["admittedSha256"]:
        parser.error("The cleanup candidate differs from the admitted previous patch.")
    if digest(args.guard_native) != features["aae-native"]["patchedSha256"]:
        parser.error("The native guard differs from the current candidate.")
    original_hashes = {str(path.resolve()): digest(path) for path in (*inputs.values(), args.legacy_core, args.guard_native)}
    output.mkdir(parents=True)
    environment = os.environ.copy()
    for variable, directory in (("LOCALAPPDATA", "local-data"), ("TEMP", "temporary"), ("TMP", "temporary")):
        folder = output / directory
        folder.mkdir(exist_ok=True)
        environment[variable] = str(folder)
    cases = []
    logs = output / "logs"
    logs.mkdir()

    def run(action: str, roots: dict[str, Path], state: Path, originals: Path | None = None,
            selected: tuple[str, ...] = (), expected_error: str | None = None) -> dict:
        command = [str(args.artifact.resolve()), action, "--workshop", str(roots["workshop"]), "--game", str(roots["game"]), "--state", str(state)]
        if originals is not None:
            command += ["--originals", str(originals)]
        if selected:
            command += ["--select", *selected]
        result = subprocess.run(command, capture_output=True, text=True, env=environment,
                                timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
        name = f"{len(list(logs.iterdir())):02d}-{action}"
        (logs / (name + ".json")).write_text(json.dumps({"command": command, "exitCode": result.returncode,
                                                       "stdout": result.stdout, "stderr": result.stderr}, indent=2))
        if expected_error is not None:
            assert result.returncode == 1 and expected_error in result.stderr, result.stderr
            return {}
        if result.returncode:
            raise AssertionError(f"Frozen {action} failed: {result.stderr}")
        return json.loads(result.stdout)

    def setup(name: str, adopted: bool) -> tuple[dict[str, Path], Path, Path]:
        directory = output / name
        roots = {"workshop": directory / "workshop", "game": directory / "game"}
        originals = directory / "canonical-originals"
        for identity, feature in features.items():
            target = roots[feature["scope"]] / feature["relativePath"]
            original = originals / feature["relativePath"]
            target.parent.mkdir(parents=True, exist_ok=True)
            original.parent.mkdir(parents=True, exist_ok=True)
            source = args.legacy_core if adopted and identity == "aae-core" else args.guard_native if adopted and identity == "aae-native" else inputs[identity]
            shutil.copyfile(source, target)
            shutil.copyfile(inputs[identity], original)
        for root in roots.values():
            (root / "unrelated-settings.txt").write_bytes(b"owned unchanged settings\r\n")
        return roots, directory / "state", originals

    for name, adopted in (("stock", False), ("adopt-prior-fixes", True)):
        roots, state, originals = setup(name, adopted)
        status = run("status", roots, state)
        assert not state.exists(), "Status wrote a backup directory."
        expected_before = {identity: "stock" for identity in features}
        if adopted:
            expected_before.update({"aae-core": "previous patch", "aae-native": "patched"})
        assert {row["id"]: row["status"] for row in status["result"]} == expected_before
        before_refusal = {identity: digest(roots[feature["scope"]] / feature["relativePath"])
                          for identity, feature in features.items()}
        for identity in sorted(retired):
            run("apply", roots, state, selected=("aae-core", identity), expected_error="removal-only")
            assert not state.exists(), "Retired apply wrote transaction state."
            assert {key: digest(roots[row["scope"]] / row["relativePath"])
                    for key, row in features.items()} == before_refusal
        assert run("apply", roots, state, originals if adopted else None)["result"]["status"] == "complete"
        for identity, feature in features.items():
            expected = feature["patchedSha256"] if identity in enabled else feature["originalSha256"]
            assert digest(roots[feature["scope"]] / feature["relativePath"]) == expected
            backup = state / "originals" / (identity + ".bin")
            if identity in enabled:
                assert digest(backup) == feature["originalSha256"]
            else:
                assert not backup.exists(), "Default apply backed up a retired stock file."
        assert {row["id"]: row["status"] for row in run("status", roots, state)["result"]} == {
            identity: "patched" if identity in enabled else "stock" for identity in features}
        assert run("remove", roots, state)["result"]["status"] == "complete"
        for identity, feature in features.items():
            assert digest(roots[feature["scope"]] / feature["relativePath"]) == feature["originalSha256"]
            assert digest(originals / feature["relativePath"]) == feature["originalSha256"]
        assert all((root / "unrelated-settings.txt").read_bytes() == b"owned unchanged settings\r\n" for root in roots.values())
        assert not (state / "journal.json").exists()
        cases.append({"case": name, "passed": True, "exactInstalledHashes": True,
                      "canonicalBackups": True, "exactRemoval": True, "unrelatedFilesPreserved": True,
                      "retiredApplyRefused": sorted(retired), "retiredTargetsUnchanged": True})
    assert all(digest(Path(path)) == value for path, value in original_hashes.items())
    report = {"passed": True, "version": manifest["version"], "artifactSha256": build["artifactSha256"],
              "manifestSha256": build["manifestSha256"], "cases": cases, "inputsPreserved": True,
              "gameLaunched": False, "gameplayValidated": False, "friendsValidated": False}
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
