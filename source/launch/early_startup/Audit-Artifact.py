"""Inspect the optional 500K launcher without executing its game path."""
import argparse
import hashlib
import json
from pathlib import Path

import pefile

parser = argparse.ArgumentParser()
parser.add_argument("--directory", type=Path, required=True)
parser.add_argument("--owned", action="store_true")
args = parser.parse_args()
name = "EarlyStartupOwned.exe" if args.owned else "BO3-500K-Zombies.exe"
# The Wine fallback in process_freeze resolves NtSuspendProcess and NtResumeProcess at run time, only after
# the job freeze reports STATUS_NOT_IMPLEMENTED under Wine. The launcher must still never import them.
forbidden_apis = {"DebugActiveProcess", "DebugActiveProcessStop", "DebugSetProcessKillOnExit",
                  "WaitForDebugEvent", "WaitForDebugEventEx", "ContinueDebugEvent", "SetThreadContext",
                  "Wow64SetThreadContext", "PssCaptureSnapshot", "SuspendThread", "NtSuspendProcess",
                  "NtSetContextThread"}
rows = []
for path in [args.directory / name, args.directory / "Bo3EnhancedHelper.dll", args.directory / "Bo3StartupGate.dll"]:
    raw = path.read_bytes()
    pe = pefile.PE(data=raw)
    imports = [{"module": dll.dll.decode(), "names": [entry.name.decode() if entry.name else f"ordinal:{entry.ordinal}"
                for entry in dll.imports]} for dll in pe.DIRECTORY_ENTRY_IMPORT]
    exports = [entry.name.decode() for entry in pe.DIRECTORY_ENTRY_EXPORT.symbols if entry.name] if hasattr(pe, "DIRECTORY_ENTRY_EXPORT") else []
    if path.name == name:
        if forbidden_apis.intersection(entry for dll in imports for entry in dll["names"]) or exports:
            raise SystemExit("The launcher has an unexpected process-control import or export.")
        if not args.owned:
            for forbidden in [b"VmStartupControlTarget", b"LoaderThreads", b"OwnedImage", b"owned-inert-endpoints",
                              b"NtCreateProcessStateChange", b"NtChangeProcessState", b"Owned serial", b"owned serial"]:
                if forbidden in raw:
                    raise SystemExit("The production launcher contains fixture state.")
    rows.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "imports": imports, "exports": exports})
(args.directory / "artifact-audit.json").write_text(json.dumps({"passed": True, "owned": args.owned,
    "scope": "Static launcher imports and fixture exclusion. No game execution.", "artifacts": rows}, indent=2), encoding="utf-8")
