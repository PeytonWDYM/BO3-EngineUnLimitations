Owned pre-entry instrumentation fixture

This fixture measures interception timing with a dummy factory and shared memory.
It does not use COM, audio devices, games, or the quiet activation adapters.
The launcher accepts fixed scenarios and a new private JSON output file.
It has no target path or arbitrary command-line mode.
Build-pinned SHA256 values identify its target, provider, consumer, and helper.
The launcher holds file locks through process exit and rejects different binaries before creating a process.
It also rejects Detours cross-architecture helper fallback. All fixture artifacts use x64.

Dependency

Use the official Microsoft Detours repository: https://github.com/microsoft/Detours.git
Use commit e4bfd6b03e50de46b47abfbd1e46b384f0c5f833, the v4.0.1 tag.
Clone and build it outside the repository. Keep its MIT license with compiled artifacts.
The build verifies the source commit, origin, and tracked source changes.
It forces a fresh library build and records the library and license hashes.

Build and E2E

Use PowerShell 7, 64-bit Python, and the Visual C++ x64 build tools.
Run source/tests/preentry/Test-Preentry.ps1 with -DetoursRoot, -Python, and a new private -OutputDirectory.
The build guard resolves directory junctions before compiler work.
The harness builds every fixture source with /W4 /WX.
It retains eight scenario results, commands, event traces, source hashes, and before/after artifact hashes.
Baseline output is deliberately nonzero. Protected factory output is zero.
Readiness must precede the imported consumer DLL, target TLS callback, and target entrypoint.
An earlier provider dependency call remains an explicit failed coverage boundary.
Denied readiness stops startup before these consumer probes.

Lifecycle and limits

The helper calls DetourRestoreAfterWith and installs one dummy-factory hook during its process-attach notification.
Its loader-lock work uses Detours, memory writes, and the current thread only.
It performs no COM/audio initialization, explicit dependent-DLL loads, waits, or thread creation in DllMain.
The provider maps an inherited owned trace handle during initialization. It performs no physical output.
This fixture has one caller thread. It does not implement safe hook removal during concurrent calls.
Each live owned reference holds an explicit helper module reference.
Removal refuses live references. The target verifies another protected call after that refusal.
The target recovers caller module ownership before releasing its live-reference pin.
Clean removal detaches the hook and restores normal dummy output.
The helper remains resident through the inserted static loader dependency until process exit.
Restoring the temporary PE imports does not remove that dependency from Windows loader bookkeeping.
The trace verifies final helper detach at process exit. The fixture does not force mid-process DLL unload.
Readiness does not cover helper dependencies that execute factory calls before helper initialization.
No result validates quiet stock startup, game activation, or an engine stability fix.

Primary references

https://github.com/microsoft/Detours/wiki/DetourCreateProcessWithDlls
https://github.com/microsoft/Detours/wiki/DetourRestoreAfterWith
https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-best-practices
