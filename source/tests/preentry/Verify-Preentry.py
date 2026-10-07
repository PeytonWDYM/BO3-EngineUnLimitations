"""Run fixed owned scenarios and retain source, artifact, and ordering evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[3]
ARTIFACTS = ("PreentryLauncher.exe", "PreentryTarget.exe", "PreentryProvider.dll", "PreentryConsumer.dll", "PreentryHelper64.dll")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == REPO or REPO in output.parents or output.exists():
        raise ValueError("Use a new private evidence directory.")
    output.mkdir(parents=True)
    before = {name: digest(args.bin / name) for name in ARTIFACTS}
    cases = []

    def run(name, scenario, directory=None):
        directory = directory or args.bin
        trace_path = output / (name + ".json")
        command = [str(directory / "PreentryLauncher.exe"), scenario, str(trace_path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=40,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        (output / (name + "-command.json")).write_text(json.dumps(command), encoding="utf-8")
        (output / (name + "-stderr.txt")).write_text(result.stderr, encoding="utf-8")
        trace = json.loads(trace_path.read_text()) if trace_path.exists() else None
        return result.returncode, trace

    def check(name, operation):
        try:
            details = operation()
            cases.append({"case": name, "passed": True, "details": details})
        except Exception as problem:
            cases.append({"case": name, "passed": False, "error": str(problem)})

    def stages(trace):
        return {event["stage"]: event for event in trace["events"]}

    def baseline():
        code, trace = run("baseline", "baseline")
        assert code != 0 and trace["unsafeCalls"] == 3
        assert all(stages(trace)[stage]["output"] == 1 for stage in ("imported-dll", "tls", "entry"))
        return trace

    def protected():
        code, trace = run("protected", "protected")
        assert code == 0 and trace["unsafeCalls"] == 0 and trace["internalErrors"] == 0
        events = trace["events"]
        ready = next(i for i, event in enumerate(events) if event["stage"] == "helper-ready")
        for stage in ("imported-dll", "tls", "entry"):
            index = next(i for i, event in enumerate(events) if event["stage"] == stage)
            assert index > ready and events[index]["ready"] == 1 and events[index]["output"] == 0
        assert stages(trace)["restore"]["output"] == 1
        return trace

    def early():
        code, trace = run("early-dependency", "early")
        assert code != 0 and trace["unsafeCalls"] == 1
        assert trace["events"][0]["stage"] == "provider-init" and trace["events"][0]["output"] == 1
        assert stages(trace)["entry"]["output"] == 0
        return trace

    def denied():
        code, trace = run("denied", "denied")
        assert code != 0 and trace["targetExit"] != 0
        assert "helper-ready" not in stages(trace)
        assert not any(stage in stages(trace) for stage in ("imported-dll", "tls", "entry"))
        return trace

    def remove(live):
        name = "live-reference" if live else "remove"
        code, trace = run(name, "live" if live else "remove")
        assert code == 0 and trace["unsafeCalls"] == 0 and trace["internalErrors"] == 0
        events = stages(trace)
        assert events["removed"]["references"] == 0 and events["helper-detach"]["references"] == 0
        assert events["helper-retained"]["output"] == 1 and events["helper-retained"]["references"] == 0
        assert events["after-remove"]["output"] == 1
        assert trace["events"][-1]["stage"] == "helper-detach"
        if live:
            assert events["unload-attempt"]["output"] == 1 and events["unload-attempt"]["references"] == 1
            assert events["remove-denied"]["references"] == 1
            denied_index = next(i for i, event in enumerate(trace["events"]) if event["stage"] == "remove-denied")
            assert trace["events"][denied_index + 1]["stage"] == "entry" and trace["events"][denied_index + 1]["output"] == 0
        return trace

    def identity():
        rejected = []
        for name in ("missing-helper", "wrong-helper", "non-owned-target"):
            directory = output / name
            shutil.copytree(args.bin, directory)
            if name == "missing-helper":
                (directory / "PreentryHelper64.dll").unlink()
            elif name == "wrong-helper":
                (directory / "PreentryHelper64.dll").write_bytes(b"wrong owned helper")
            else:
                shutil.copyfile(directory / "PreentryLauncher.exe", directory / "PreentryTarget.exe")
            code, trace = run(name, "protected", directory)
            assert code != 0 and trace is None
            rejected.append(name)
        return rejected

    def output_boundary():
        existing = output / "existing.json"
        existing.write_text("retain", encoding="utf-8")
        destinations = (REPO, REPO / "preentry-review-output.json", existing)
        for path in destinations:
            result = subprocess.run([str(args.bin / "PreentryLauncher.exe"), "protected", str(path)],
                                    capture_output=True, text=True, timeout=10,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode != 0
        assert not (REPO / "preentry-review-output.json").exists() and existing.read_text() == "retain"
        junction = output / "repository-junction"
        result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(REPO)],
                                capture_output=True, text=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, result.stderr
        alias = junction / "preentry-review-output.json"
        result = subprocess.run([str(args.bin / "PreentryLauncher.exe"), "protected", str(alias)],
                                capture_output=True, text=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode != 0 and not alias.exists()
        build_result = subprocess.run(["pwsh.exe", "-NoProfile", "-File",
                                      str(REPO / "source/launch/preentry/Build-Preentry.ps1"),
                                      "-DetoursRoot", str(output / "missing-dependency"),
                                      "-OutputDirectory", str(junction / "preentry-review-build")],
                                     capture_output=True, text=True, timeout=10,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        assert build_result.returncode != 0 and "outside the repository" in build_result.stderr
        assert not (REPO / "preentry-review-build").exists()
        junction.rmdir()
        return {"repositoryAndExistingRefused": True, "junctionRefusedBeforeDependencyAndBuild": True}

    check("baseline exposes all three early calls", baseline)
    check("ready before imported DLL TLS and entrypoint", protected)
    check("dependency call before readiness fails coverage", early)
    check("denied readiness stops startup", denied)
    check("live reference prevents removal", lambda: remove(True))
    check("clean removal and normal dummy output", lambda: remove(False))
    check("fixed fixture identity rejects missing wrong and non-owned binaries", identity)
    check("private output boundary", output_boundary)
    after = {name: digest(args.bin / name) for name in ARTIFACTS}
    report = {"passed": all(case["passed"] for case in cases) and before == after, "cases": cases,
              "artifactSha256Before": before, "artifactSha256After": after,
              "sourceSha256": {str(path.relative_to(REPO)): digest(path)
                               for folder in (REPO / "source/launch/preentry", REPO / "source/tests/preentry")
                               for path in folder.iterdir() if path.is_file()},
              "limits": "Owned dummy factory only. No game, audio device, or stock startup compatibility is validated."}
    (output / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "casesPassed": sum(case["passed"] for case in cases), "total": len(cases)}))
    return 0 if report["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
