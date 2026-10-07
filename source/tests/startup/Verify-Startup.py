"""Exercise controlled startup milestones with owned memory sinks only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import pefile

REPO = Path(__file__).resolve().parents[3]
BINARIES = ("StartupLauncher.exe", "StartupTarget.exe", "StartupFactories.dll", "StartupConsumer.dll", "StartupHelper64.dll")
STOP_EXIT = 0xE0510001

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--worker-starts", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == REPO or REPO in output.parents or output.exists():
        raise ValueError("Use a new private evidence directory.")
    output.mkdir(parents=True)
    before = {name: digest(args.bin / name) for name in BINARIES}
    cases = []

    def run(scenario):
        trace_path = output / (scenario + ".json")
        command = [str(args.bin / "StartupLauncher.exe"), scenario, str(trace_path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=40,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        (output / (scenario + "-command.json")).write_text(json.dumps(command, indent=2), encoding="utf-8")
        (output / (scenario + "-stderr.txt")).write_text(result.stderr, encoding="utf-8")
        return result.returncode, json.loads(trace_path.read_text())

    def check(name, operation):
        try:
            cases.append({"case": name, "passed": True, "details": operation()})
        except Exception as problem:
            cases.append({"case": name, "passed": False, "error": repr(problem)})

    def baseline():
        code, trace = run("baseline")
        assert code != 0 and trace["rawPublications"] > 0
        assert trace["renderPackets"] > trace["silentRenderPackets"]
        assert trace["soundPlays"] > trace["silentSoundPlays"]
        assert trace["loaderConstructors"] == 0
        return trace

    def early(prefix, phase):
        results = []
        for api in ("com", "sound"):
            code, trace = run(prefix + "-" + api)
            assert code != 0 and trace["targetExit"] == STOP_EXIT
            assert trace["constructors"] == trace["providerCalls"] == trace["rawPublications"] == 0
            events = trace["events"]
            stop = next(event for event in events if event["stage"] == "early-stop")
            assert stop["hooksReady"] == 1 and stop["runtimeReady"] == 0 and stop["phase"] == phase
            assert not any(event["stage"] in ("raw-factory", "consumer-after", "runtime-ready", "helper-detach") for event in events)
            assert not any(event["stage"] == "entry-probe" for event in events)
            if prefix == "import":
                assert not any(event["stage"] == "tls-probe" for event in events)
            results.append(trace)
        return results

    def dependency():
        code, trace = run("dependency")
        assert code != 0 and trace["uncovered"] == 1
        assert trace["constructors"] == trace["providerCalls"] == trace["rawPublications"] == 0
        earlier = next(event for event in trace["events"] if event["stage"] == "uncovered")
        assert earlier["hooksReady"] == earlier["runtimeReady"] == 0 and earlier["phase"] == "dependency"
        return trace

    def success(scenario):
        code, trace = run(scenario)
        assert code == 0 and trace["targetExit"] == 0 and trace["errors"] == trace["uncovered"] == 0
        assert trace["constructors"] == 1 and trace["loaderConstructors"] == 0
        assert trace["providerCalls"] > 0 and trace["generations"] >= 8 and trace["rawPublications"] == 0
        assert trace["renderPackets"] > 0 and trace["renderPackets"] == trace["silentRenderPackets"]
        assert trace["soundPlays"] >= 6 and trace["soundPlays"] == trace["silentSoundPlays"]
        assert trace["callbacks"] == 3 and trace["unsafeBranch"] == trace["aborted"] == 0
        events = trace["events"]
        assert sum(event["stage"] == "callback" for event in events) == trace["callbacks"]
        ready = next(i for i, event in enumerate(events) if event["stage"] == "hooks-ready")
        runtime = next(i for i, event in enumerate(events) if event["stage"] == "runtime-ready")
        assert ready < runtime
        for i, event in enumerate(events):
            if event["stage"] == "root-enter":
                assert i > runtime and event["hooksReady"] == event["runtimeReady"] == 1
            if event["stage"] in ("render-publish", "buffer-publish"):
                assert event["value"] == 0
            if event["stage"] in ("render-output", "sound-output"):
                assert event["value"] == 1
        assert any(event["stage"] == "ordinal-match" and event["value"] == 1 for event in events)
        assert events[-1]["stage"] == "helper-detach"
        return trace

    def worker():
        trace = success("worker")
        assert trace["workerThread"] != 0 and trace["callbackThread"] == trace["workerThread"]
        assert all(event["thread"] == trace["workerThread"] for event in trace["events"] if event["stage"] == "root-enter")
        return trace

    def failures():
        results = []
        code, trace = run("denied")
        assert code != 0 and trace["targetExit"] != 0
        assert trace["constructors"] == trace["providerCalls"] == trace["rawPublications"] == 0
        assert not any(event["stage"] in ("hooks-ready", "runtime-ready", "imported-probe", "tls-probe", "entry-probe") for event in trace["events"])
        results.append(trace)
        for scenario, expected in (("unsupported-qi", -2147467262), ("unsupported-clear", -2005401450)):
            code, trace = run(scenario)
            assert code != 0 and trace["targetExit"] == STOP_EXIT and trace["aborted"] == 1
            assert trace["abortHresult"] == expected and trace["unsafeBranch"] == 0
            assert trace["rawPublications"] == trace["soundPlays"] == 0
            assert not any(event["stage"] in ("native-failure", "consumer-after", "helper-detach") for event in trace["events"])
            results.append(trace)
        return results

    def lifetime():
        trace = success("live")
        events = trace["events"]
        denied = next(i for i, event in enumerate(events) if event["stage"] == "removal-denied")
        released = next(i for i, event in enumerate(events) if event["stage"] == "references-released")
        destroyed = next(i for i, event in enumerate(events) if event["stage"] == "runtime-destroyed")
        removed = next(i for i, event in enumerate(events) if event["stage"] == "hooks-removed")
        assert denied < released < destroyed < removed
        assert any(event["stage"] == "render-output" and event["value"] == 1 for event in events[denied:released])
        assert any(event["stage"] == "sound-output" and event["value"] == 1 for event in events[denied:released])
        assert any(event["stage"] == "helper-retained" and event["value"] == 1 for event in events[removed:])
        return trace

    def guards():
        outcomes = []
        for name in ("StartupTarget.exe", "StartupHelper64.dll"):
            for missing in (False, True):
                folder = output / ("guard-" + name + ("-missing" if missing else "-wrong"))
                folder.mkdir()
                for binary in BINARIES:
                    shutil.copy2(args.bin / binary, folder / binary)
                candidate = folder / name
                if missing:
                    candidate.unlink()
                else:
                    candidate.write_bytes(candidate.read_bytes() + b"wrong identity")
                trace = folder / "must-not-exist.json"
                result = subprocess.run([str(folder / "StartupLauncher.exe"), "entry", str(trace)],
                                        capture_output=True, text=True, timeout=10)
                assert result.returncode != 0 and not trace.exists()
                outcomes.append({"file": name, "missing": missing, "stderr": result.stderr})
        junction = output / "repository-junction"
        junction_script = output / "make-private-junction.ps1"
        junction_script.write_text("param([string]$Path,[string]$Target)\nNew-Item -ItemType Junction -Path $Path -Target $Target | Out-Null\n", encoding="utf-8")
        subprocess.run(["pwsh", "-NoProfile", "-File", str(junction_script),
                        "-Path", str(junction), "-Target", str(REPO)], check=True, capture_output=True, text=True)
        try:
            for destination in (REPO, REPO / "forbidden-startup-output", junction / "forbidden-startup-output"):
                trace = destination / "must-not-exist.json"
                result = subprocess.run([str(args.bin / "StartupLauncher.exe"), "entry", str(trace)],
                                        capture_output=True, text=True, timeout=10)
                assert result.returncode != 0 and not trace.exists()
                for script in (REPO / "source/launch/startup/Build-Startup.ps1", REPO / "source/tests/startup/Test-Startup.ps1"):
                    command = ["pwsh", "-NoProfile", "-File", str(script), "-OutputDirectory", str(destination),
                               "-DetoursRoot", str(output / "absent-Detours")]
                    if script.name.startswith("Test"):
                        command += ["-Python", "absent-python"]
                    rejected = subprocess.run(command, capture_output=True, text=True, timeout=10)
                    assert rejected.returncode != 0 and "outside the repository" in rejected.stderr
                    outcomes.append({"script": script.name, "destination": str(destination), "stderr": rejected.stderr})
        finally:
            junction.rmdir()
        for name in ("StartupTarget.exe", "StartupConsumer.dll"):
            with pefile.PE(str(args.bin / name)) as image:
                shim = next(item for item in image.DIRECTORY_ENTRY_IMPORT if item.dll == b"StartupFactories.dll")
                assert any(item.name is None and item.ordinal == 11 for item in shim.imports)
        return outcomes

    if args.worker_starts:
        from WorkerCases import register
        register(check, run, success, early, dependency)
    else:
        check("raw memory baseline", baseline)
        check("covered imported DLL activation stops", lambda: early("import", "imported"))
        check("covered startup TLS activation stops", lambda: early("tls", "tls"))
        check("earlier dependency remains uncovered", dependency)
        check("post-loader entry separate and shared identities", lambda: [success("entry"), success("shared")])
        check("post-loader worker and callback recreation", worker)
        check("denied readiness and unsupported DirectSound stop", failures)
        check("live wrappers block removal and clean stop", lifetime)
        check("fixed identity ordinal imports and physical output guards", guards)
    after = {name: digest(args.bin / name) for name in BINARIES}
    dependencies = [*list((REPO / "source/launch/activation").glob("*")),
                    *list((REPO / "source/launch/quiet").glob("*")),
                    *list((REPO / "source/tests/activation").glob("*")),
                    *list((REPO / "source/tests/quiet").glob("*")),
                    REPO / "source/launch/preentry/Identity.cpp", REPO / "source/launch/preentry/Identity.h"]
    sources = [*list((REPO / "source/launch/startup").glob("*")),
               *list((REPO / "source/tests/startup").glob("*")),
               REPO / "research/quiet-startup-failure-cases.txt", *dependencies]
    report = {"passed": all(case["passed"] for case in cases) and before == after, "cases": cases,
              "artifactSha256Before": before, "artifactSha256After": after,
              "sourceSha256": {str(path.relative_to(REPO)): digest(path) for path in sources if path.is_file()},
              "dependency": json.loads((args.bin / "detours-provenance.json").read_text(encoding="utf-8-sig")),
              "limits": "Owned phase contract and memory sinks only. Earlier dependencies remain uncovered. No Windows factory, device, driver, game, or concurrent removal validation."}
    (output / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "passedCases": sum(case["passed"] for case in cases), "total": len(cases)}))
    return 0 if report["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
