"""Owned actual SDK interception. This entrypoint runs memory mode only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import pefile

ROOT = Path(__file__).resolve().parents[3]
FILES = ("SdkLauncher.exe", "SdkTarget.exe", "SdkInterceptConsumer.dll", "SdkInterceptHelper.dll")
STOP = 0xe0520001
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents or output.exists(): raise ValueError("Use a new private output directory.")
    output.mkdir(parents=True)
    before = {name: sha(args.bin/name) for name in FILES}
    cases = []
    def run(scenario):
        path = output/(scenario+".json")
        cmd = [str(args.bin/FILES[0]), "memory", scenario, str(path)]
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
        (output/(scenario+"-command.json")).write_text(json.dumps(cmd, indent=2))
        (output/(scenario+"-stderr.txt")).write_text(process.stderr)
        return process.returncode, json.loads(path.read_text())
    def case(name, action):
        try: cases.append({"case": name, "passed": True, "details": action()})
        except Exception as error: cases.append({"case": name, "passed": False, "error": repr(error)})
    def silent(trace):
        assert trace["physicalAudioCalls"] == 0
        assert trace["renderPackets"] > 0 and trace["renderPackets"] == trace["silentRenderPackets"]
        assert trace["soundObservations"] > 0 and trace["soundObservations"] == trace["silentSoundObservations"]
        assert trace["fullClears"] >= 2 and trace["silentReleases"] >= 5 and trace["callbackLive"] == 0
        assert trace["sdkCom"] and trace["sdkSound"] and trace["sdkThread"]
        for address, module in zip((trace["sdkCom"],trace["sdkSound"],trace["sdkThread"]),trace["sdkModules"]):
            path=Path(module["path"])
            assert path.parent == Path(os.environ["SystemRoot"])/"System32"
            assert module["base"]+module["rva"] == address and module["rva"] < module["imageSize"]
            with pefile.PE(str(path)) as image:
                assert image.OPTIONAL_HEADER.SizeOfImage == module["imageSize"]
                assert image.FILE_HEADER.TimeDateStamp == module["timestamp"]
            module["sha256"]=sha(path)
        stages = [event["stage"] for event in trace["events"]]
        assert stages.index("first-silent") < stages.index("start")
        cleared = set()
        for event in trace["events"]:
            if event["stage"] == "full-clear": cleared.add(event["generation"])
            if event["stage"] == "play": assert event["generation"] in cleared
            if event["stage"] == "root-enter":
                assert event["caller"] != 0 and event["pid"] == trace["targetPid"]
                module=event["callerModule"]
                assert Path(module["path"]).name == "SdkInterceptConsumer.dll"
                assert module["base"]+module["rva"] == event["caller"] and module["rva"] < module["imageSize"]
    def baseline():
        code, trace = run("baseline")
        silent(trace)
        assert code != 0 and trace["targetExit"] == 0 and trace["rawPublications"] > 0
        return trace
    def protected(scenario):
        code, trace = run(scenario)
        silent(trace)
        assert code == trace["targetExit"] == 0 and trace["rawPublications"] == trace["errors"] == trace["aborted"] == 0
        assert trace["constructors"] == 1 and trace["generations"] == 7 and trace["callbackCalls"] == 3
        assert trace["nonAudioCalls"] >= 1
        assert all(event["value"] == 0 for event in trace["events"] if event["stage"] in ("render-publish", "buffer-publish"))
        return trace
    def worker():
        trace = protected("worker")
        stages = [event["stage"] for event in trace["events"]]
        assert trace["matched"] == 1 and trace["creatorTid"] != trace["workerTid"] == trace["returnedTid"]
        assert trace["flags"] == 4 and trace["parameter"] == 14 and trace["priorityResult"] != 0 and trace["resumeResult"] == 1
        assert trace["stackSize"] == trace["attributesPresent"] == 0 and trace["returnedHandle"] != 0
        assert stages.index("resume") < stages.index("gate") < stages.index("runtime-ready") < stages.index("setup") < stages.index("dispatch")
        assert stages.index("dispatch") < stages.index("root-enter")
        assert stages.index("references-released") < stages.index("joined") < stages.index("runtime-closed") < stages.index("hooks-removed")
        assert stages.index("joined") < stages.index("entry")
        assert "removal-denied" in stages and trace["callbackTid"] == trace["workerTid"]
        return trace
    def unmatched():
        result = []
        for name, context, setups, expected in (("wrong-entry",14,0,0x510e),("wrong-context",13,1,0x520d)):
            code, trace = run(name)
            assert code == trace["targetExit"] == 0 and trace["constructors"] == trace["providerCalls"] == trace["matched"] == 0
            assert trace["unmatched"] >= 1 and trace["nativeSetups"] == setups and trace["parameter"] == context
            assert trace["physicalAudioCalls"] == trace["rawPublications"] == 0
            joined = next(event for event in trace["events"] if event["stage"] == "joined")
            assert joined["value"] == expected
            result.append(trace)
        return result
    def cold():
        result=[]
        for name in ("import-com","import-sound","tls-com","tls-sound"):
            code,trace=run(name)
            assert code != 0 and trace["targetExit"] == STOP
            assert trace["constructors"] == trace["providerCalls"] == trace["physicalAudioCalls"] == trace["rawPublications"] == 0
            assert any(event["stage"] == "root-enter" for event in trace["events"])
            assert any(event["stage"] == "cold-stop" for event in trace["events"])
            assert not any(event["stage"] in ("runtime-ready","entry","detach") for event in trace["events"])
            result.append(trace)
        return result
    def denied():
        result=[]
        for name in ("denied","missing-handshake"):
            code,trace=run(name)
            assert code != 0 and trace["targetExit"] == STOP
            assert trace["constructors"] == trace["nativeSetups"] == trace["providerCalls"] == trace["physicalAudioCalls"] == 0
            if name == "missing-handshake": assert not any(event["stage"] == "root-enter" for event in trace["events"])
            result.append(trace)
        return result
    def unsupported():
        result=[]
        for name,hr in (("no-buffer8",-2147467262),("clear-failed",-2005401450),("reentrant",-2147483638)):
            code,trace=run(name)
            assert code != 0 and trace["targetExit"] == STOP and trace["abortHresult"] == hr
            assert trace["physicalAudioCalls"] == trace["rawPublications"] == trace["plays"] == 0
            if name == "reentrant":
                nested=next(event for event in trace["events"] if event["stage"] == "recursive-stop")
                assert nested["depth"] >= 1 and nested["outer"] == 1 and nested["caller"] != 0
                root=next(event for event in trace["events"] if event["stage"] == "root-enter" and event["depth"] >= 1)
                assert Path(root["callerModule"]["path"]).name == "SdkInterceptHelper.dll"
                assert root["callerModule"]["base"]+root["callerModule"]["rva"] == nested["caller"]
                assert trace["providerCalls"] == 1
            result.append(trace)
        return result
    def guards():
        result=[]
        for name in ("SdkTarget.exe","SdkInterceptConsumer.dll","SdkInterceptHelper.dll"):
            folder=output/("wrong-"+name); folder.mkdir()
            for binary in FILES: shutil.copy2(args.bin/binary,folder/binary)
            candidate=folder/name; candidate.write_bytes(candidate.read_bytes()+b"wrong build")
            trace=folder/"must-not-exist.json"
            process=subprocess.run([str(folder/FILES[0]),"memory","entry",str(trace)],capture_output=True,text=True,timeout=10)
            assert process.returncode != 0 and not trace.exists()
            result.append(process.stderr)
        junction=output/"repository-junction"
        escaped=str(junction).replace("'","''")
        repo=str(ROOT).replace("'","''")
        created=subprocess.run(["pwsh","-NoProfile","-Command",
            "New-Item -ItemType Junction -Path '"+escaped+"' -Target '"+repo+"' | Out-Null"],capture_output=True,text=True,timeout=10)
        assert created.returncode == 0, created.stderr
        refusals=[]
        try:
            destinations=(ROOT,ROOT/"must-not-create-sdk-evidence",junction/"must-not-create-sdk-evidence")
            for destination in destinations:
                command=[str(args.bin/FILES[0]),"memory","entry",str(destination)]
                process=subprocess.run(command,capture_output=True,text=True,timeout=10)
                assert process.returncode != 0 and "outside the repository" in process.stderr
                for script, extra in ((ROOT/"source/launch/intercept/Build-Intercept.ps1",[]),
                                      (ROOT/"source/tests/intercept/Test-Intercept.ps1",["-Python","must-not-discover-python"])):
                    command=["pwsh","-NoProfile","-File",str(script),"-OutputDirectory",str(destination),
                             "-DetoursRoot","must-not-discover-detours",*extra]
                    denied=subprocess.run(command,capture_output=True,text=True,timeout=10)
                    assert denied.returncode != 0 and "outside the repository" in denied.stderr
                    refusals.append({"command":command,"stderr":denied.stderr})
                if destination != ROOT: assert not destination.exists()
        finally:
            # Remove only this verified private junction, never its repository target.
            assert junction.parent == output and junction.resolve() == ROOT
            os.rmdir(junction)
        with pefile.PE(str(args.bin/"SdkInterceptHelper.dll")) as image:
            imports={item.dll.decode().lower():[symbol.name.decode() if symbol.name else "ordinal:"+str(symbol.ordinal) for symbol in item.imports] for item in image.DIRECTORY_ENTRY_IMPORT}
        assert not any("sdkinterceptconsumer" in dll or "sdktarget" in dll for dll in imports)
        for function in ("CoCreateInstance","CreateThread"):
            assert any(function in names for names in imports.values())
        assert "dsound.dll" in imports and ("DirectSoundCreate8" in imports["dsound.dll"] or "ordinal:11" in imports["dsound.dll"])
        with pefile.PE(str(args.bin/"SdkInterceptConsumer.dll")) as image:
            sdk={item.dll.decode().lower():[symbol.name.decode() if symbol.name else "ordinal:"+str(symbol.ordinal) for symbol in item.imports] for item in image.DIRECTORY_ENTRY_IMPORT}
        assert any("CoCreateInstance" in names for names in sdk.values()) and any("CreateThread" in names for names in sdk.values())
        assert "dsound.dll" in sdk and ("DirectSoundCreate8" in sdk["dsound.dll"] or "ordinal:11" in sdk["dsound.dll"])
        return {"identityRefusals":result,"outputRefusals":refusals,"helperImports":imports,"consumerImports":sdk}
    def rejected_containment():
        result=[]
        for name,extra in (("contained-memory",0),("contained-class",64),("contained-iid",128),
                           ("contained-context",256),("contained-aggregation",512),("contained-output",0),
                           ("contained-null-output",1024),("contained-callback",0)):
            code,trace=run(name)
            assert code != 0 and trace["targetExit"] == STOP and trace["abortHresult"] == -2147483638
            assert trace["physicalAudioCalls"] == trace["rawPublications"] == trace["plays"] == 0
            assert trace["soundScopes"] == trace["containedCalls"] == trace["originalComCalls"] == 0
            checked=next(e for e in trace["events"] if e["stage"]=="admission-checked")
            assert checked["depth"]==1 and checked["outer"]==2
            assert checked["failedAdmission"] & (1|2|4096|8192) == 1|2|4096|8192
            if extra: assert checked["failedAdmission"] & extra
            assert checked["outputNull"]==2 and not checked["failedAdmission"] & 2048
            if name=="contained-output":
                assert any(e["stage"]=="rejection-requested" and e["api"]==1 and e["value"]==1 for e in trace["events"])
            assert checked["scopeSerial"]==checked["scopeThread"]==checked["containedActive"]==0
            result.append(trace)
        return {"traces":result,"claim":"Actual SDK memory negatives fail several predicates. No genuine OriginalSound authority or isolated positive-scope branch was simulated."}
    def other_thread():
        code,trace=run("contained-thread")
        assert code==trace["targetExit"]==0 and trace["otherThreadWrapped"]==1
        assert trace["physicalAudioCalls"]==trace["rawPublications"]==trace["soundScopes"]==trace["containedCalls"]==0
        stages=[e["stage"] for e in trace["events"]]
        assert "other-thread-wrapped" in stages and "hooks-removed" in stages
        return trace
    def wrong_windows_identity():
        result=[]
        for name,bit in (("contained-identity",32768),("contained-live-bytes",16384)):
            code,trace=run(name)
            assert code != 0 and trace["targetExit"]==STOP
            assert trace["physicalAudioCalls"]==trace["providerCalls"]==trace["constructors"]==trace["soundScopes"]==0
            event=next(e for e in trace["events"] if e["stage"]=="live-identity")
            assert event["failedAdmission"] & bit
            result.append(trace)
        return {"traces":result,"claim":"The fixed memory fixture changes expected identity fields only. The real Windows DLL stays untouched."}
    case("silent raw memory provider baseline through SDK hooks",baseline)
    case("actual SDK roots wrap entry recreation and callbacks",lambda:protected("entry"))
    case("actual SDK thread gate preserves suspended worker",worker)
    case("unmatched SDK thread entry or context stays cold",unmatched)
    case("cold SDK imported and TLS roots stop inside hook",cold)
    case("readiness and missing-hook handshake stop before provider",denied)
    case("unsupported and actual SDK recursive calls fail closed",unsupported)
    case("fixed identities and actual SDK import boundaries",guards)
    case("memory provider and caller arguments cannot inherit containment",rejected_containment)
    case("another native thread keeps ordinary wrapped SDK behavior",other_thread)
    case("wrong expected Windows tuple and live bytes reject before provider",wrong_windows_identity)
    after={name:sha(args.bin/name) for name in FILES}
    paths=[*list((ROOT/"source/launch/intercept").glob("*")),*list((ROOT/"source/tests/intercept").glob("*")),ROOT/"research/sdk-interception-failure-cases.txt"]
    for folder in ("source/launch/activation","source/launch/quiet","source/tests/activation","source/tests/quiet","source/tests/audio-driver","source/launch/preentry"):
        paths.extend((ROOT/folder).glob("*"))
    report={"passed":all(item["passed"] for item in cases) and before==after,"cases":cases,
            "artifactSha256Before":before,"artifactSha256After":after,"sourceSha256":{str(path.relative_to(ROOT)):sha(path) for path in paths if path.is_file()},
            "dependency":json.loads((args.bin/"detours-provenance.json").read_text(encoding="utf-8-sig")),
            "limits":"Owned actual SDK API interception with memory providers only. No physical run. Earlier dependencies, stock chronology, global output coverage, drivers, and concurrent removal remain unvalidated."}
    (output/"result.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({"passed":report["passed"],"passedCases":sum(item["passed"] for item in cases),"total":len(cases)}))
    return 0 if report["passed"] else 1
if __name__=="__main__": raise SystemExit(main())
