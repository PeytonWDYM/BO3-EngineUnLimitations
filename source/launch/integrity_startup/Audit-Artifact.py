"""Audit the optional integrity startup launcher without executing it."""
import argparse
import hashlib
import json
from pathlib import Path

import pefile

p = argparse.ArgumentParser()
p.add_argument("--directory", type=Path, required=True)
p.add_argument("--owned", action="store_true")
p.add_argument("--resources", action="store_true")
a = p.parse_args()
name = "NativePublicationResourcesOwned.exe" if a.resources else "IntegrityStartupOwnedFixture.exe" if a.owned else "BO3-Integrity-Zombies.exe"
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
            for forbidden in [b"OwnedImage", b"VmStartupControlTarget", b"LoaderThreads", b"owned-inert-endpoints",
                              b"NtCreateProcessStateChange", b"NtChangeProcessState", b"Owned serial", b"owned serial"]:
                assert forbidden not in raw, forbidden
    rows.append({"path": str(file), "sha256": hashlib.sha256(raw).hexdigest(), "imports": imports, "exports": exports})
(a.directory / "artifact-audit.json").write_text(json.dumps({"passed": True, "owned": a.owned,
    "scope": "No debugger attachment, context writes, PSS capture, or production fixture state.",
    "artifacts": rows}, indent=2), encoding="utf-8")
