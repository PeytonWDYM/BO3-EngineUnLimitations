Experimental late CRT startup candidate

This launcher creates one owned child with the fixed VM helper and a separate CRT gate helper.
The gate checks its process payload, primary thread, exact native caller bytes, outer CRT return, and native entry frame.
Only that callback can signal readiness and wait outside loader callbacks.

The parent attaches after readiness. It never writes hardware debug registers.
The write stop must belong to the new ntdll!DbgUiRemoteBreakin thread at ntdll!DbgBreakPoint.
A worker breakpoint at that same export retains its native exception handling.
At this stop, the parent checks all 82 code guards, 19 stock count instructions, and zero VM and migration storage.
The fixed transaction has 42 edits: 500,001 server records, 18 client roots, and a 32 MiB migration buffer.
It preserves 65,000 client records and imports the stock eight-root Zombies format.

The parent commits the edits and relay lifetime before it continues the debug event.
It detaches, checks that the debugger is absent, then releases the same waiting callback.
A failure before continuation rolls back while the debug event remains pending.
A failure after commit closes the owned child. It does not roll back running code or free committed relays.
Failure cleanup preserves the original exception and drains the child for at most five seconds.
The production startup deadline remains 30 seconds.

Run BO3-Late-Zombies.exe <BlackOps3.exe> [game arguments].
The launcher accepts only the compiled executable and helper hashes. It has no profile or capacity override.
Keep both fixed helper DLLs beside the launcher. The launcher retains child ownership until process exit.
It does not modify the game executable, installation, or Steam configuration.

Receipts use schema 1, candidate 0.1.0-test.3, and startupMethod late-crt-gate.
Their filename binds the process creation FILETIME and PID under LocalAppData/BO3 Engine UnLimitations/sessions.
The writer rejects directory redirection, reparse points, and existing filenames. It uses CREATE_NEW and locked directory handles.
The receipt reports committed, detached, debuggerAbsent, and released separately.
liveAllocationValidated remains false. Callback release does not prove allocation, AAE loading, migration, or multiplayer.

Build.ps1 requires new private output, the pinned Detours library, a verified VM helper build, and the fixed production gate build.
It compiles the native source list from Compile.ps1. Steam transport sources have a separate receipt to avoid a hash cycle.
source/tests/late-startup/Build.ps1 runs the failure-first owned suite against inert captured bytes.
The fixture executes its own code and the reviewed helpers. It never executes BO3 native code or starts Steam.
Its artifacts retain exact transaction bytes, rollback bytes, protections, event identities, receipts, and handle tables.

On Windows 11 build 26200, a later debugger cycle can retain one OS WaitCompletionPacket until parent exit.
The focused handle tables show no extra owned Process, Thread, Event, or File handles.
PSS-only capture leaves handle counts unchanged. A cycle without PSS also retains the packet.
The source does not close an undocumented OS handle. Production owns one child and then exits.
The exact OS retention cause and actual protected-game late attachment remain unverified.
