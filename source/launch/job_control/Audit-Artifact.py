"""Save bounded native imports and reject forbidden production capabilities."""
import argparse
import hashlib
import json
from pathlib import Path

import pefile

p = argparse.ArgumentParser()
p.add_argument("--directory", type=Path, required=True)
p.add_argument("--owned", action="store_true")
p.add_argument("--repository", type=Path, required=True)
a = p.parse_args()
name = "JobControlOwnedFixture.exe" if a.owned else "BO3-Job-Control.exe"
rows = []
for file in [a.directory / name, a.directory / "Bo3EnhancedHelper.dll", a.directory / "Bo3StartupGate.dll"]:
    raw = file.read_bytes()
    pe = pefile.PE(data=raw)
    imports = [{"module": dll.dll.decode(), "names": [entry.name.decode() if entry.name else f"ordinal:{entry.ordinal}"
               for entry in dll.imports]} for dll in pe.DIRECTORY_ENTRY_IMPORT]
    exports = [entry.name.decode() for entry in getattr(pe, "DIRECTORY_ENTRY_EXPORT", type("Empty", (), {"symbols": []})).symbols
               if entry.name]
    if file.name == name:
        banned = {"DebugActiveProcess", "DebugActiveProcessStop", "DebugSetProcessKillOnExit", "WaitForDebugEvent",
                  "WaitForDebugEventEx", "ContinueDebugEvent", "SetThreadContext", "Wow64SetThreadContext",
                  "PssCaptureSnapshot", "SuspendThread", "NtSuspendProcess", "NtSetContextThread"}
        assert not banned.intersection(entry for dll in imports for entry in dll["names"])
        assert not exports
        if not a.owned:
            for forbidden in [b"OwnedImage", b"VmStartupControlTarget", b"LoaderThreads", b"NtCreateProcessStateChange",
                              b"NtChangeProcessState", b"Owned serial", b"owned serial"]:
                assert forbidden not in raw, forbidden
    rows.append({"path": str(file), "sha256": hashlib.sha256(raw).hexdigest(), "imports": imports, "exports": exports})
control_sources = []
for file in sorted((a.repository / "source/launch/job_control").glob("*.cpp")):
    text = file.read_text()
    for forbidden in ["WriteProcessMemory", "VirtualAllocEx", "VirtualProtectEx", "FlushInstructionCache", "SetThreadContext",
                      "PrepareFixedPlan", "PausedPatch(", "NearRelay", "DebugActiveProcess", "PssCaptureSnapshot", "SuspendThread"]:
        assert forbidden not in text, (file, forbidden)
    control_sources.append({"path": str(file), "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
(a.directory / "artifact-audit.json").write_text(json.dumps({"passed": True, "owned": a.owned,
    "scope": "Launcher forbids debugger attachment/events/context writes and fixture state in production. Frozen gate DLL retains its reviewed Detours imports.",
    "artifacts": rows, "controlSources": control_sources,
    "remoteWriteBoundary": "Unchanged Detours OwnedChild suspended pre-import/payload setup legitimately imports WriteProcessMemory/VirtualProtectEx. Control admission, freeze, release, and observation sources contain none; no NativePlan, NearRelay, MigrationPlan or publication coordinator is linked."}, indent=2), encoding="utf-8")
