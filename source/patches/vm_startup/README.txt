VM startup allocation gate: owned fixture only

DebugGate.cpp stops a DEBUG_ONLY_THIS_PROCESS child at its first allocator entry.
It arms each thread before Windows permits that thread to execute user code.
The hardware breakpoint survives the owned target's replacement of encrypted bytes.

At the gate, Windows stops all target threads.
The gate requires null server pool and hash pointers and exact code bytes.
Every edit must have an enclosing byte check.
The gate changes all count consumers before it permits allocation to continue.
A failed write keeps the child stopped for caller termination.
An uncommitted paused patch restores attempted bytes and their original page protection.

The gate restores its debug registers before the readiness callback.
The callback runs before any owned count consumer completes.
The debugger remains attached until child exit.
Several threads can have pending allocation exceptions after the first event.
Immediate detach failed the concurrent fixture with an unhandled single-step exception.
Current exception handling distinguishes queued owned traps from trace-flag exceptions at the same address.
This behavior has owned-process evidence only. It does not prove stock BO3 exception compatibility.

Test fixture

Use PowerShell 7 and a new private output directory:
  pwsh -NoProfile -File source/tests/vm-startup/Test.ps1 -OutputDirectory PRIVATE_NEW_DIRECTORY

The test builds a fixed owned target and binds its launcher to the target's SHA-256.
The launcher accepts fixed scenarios only. It accepts no game executable or process ID.
The test records 18 native cases, allocation bytes, visited IDs, and deterministic ID receipts.
Successful cases cover 500,000 and 1,000,000 usable slots.
Other cases cover TLS allocation, suspended workers, concurrent workers, refusal, and exception forwarding.

Pre-imported helper composition

Test-Composed.ps1 reuses the pinned Detours pre-import loader and the exported Bo3VmStateBindings POD storage.
Supply a private output directory, the pinned Detours source directory, and Python with pefile:
  pwsh -NoProfile -File source/tests/vm-startup/Test-Composed.ps1 -OutputDirectory PRIVATE_NEW_DIRECTORY -DetoursRoot PRIVATE_PINNED_DETOURS -Python PRIVATE_PYTHON

The helper restores temporary imports and publishes loader readiness before the imported consumer and TLS.
The parent writes all 48 binding bytes and two owned callback hooks while the allocation gate stops every thread.
The readiness callback follows readback of both count edits, both hooks, and the binding record.
A readiness refusal restores those edits and original memory protection before child termination.
The 16 composed cases include wrong-helper identity refusal and native concurrent hook calls.
All three owned helper objects lack a dynamic C++ initializer table.
The exact helper imports KERNEL32 only and has 24 raw TLS bytes with no TLS callbacks.
Its linked CRT and Detours still import loader APIs. The inventory does not prove platform initialization avoids those calls.
The composed helper contains the state bridge but exercises owned callback hooks and its TLS-clear export.
It does not execute the captured game's serializer addresses or engine error path.

Owned native error routing

StateErrors.h exposes a separate 32-byte zero-POD error binding record.
ReadStateOrDrop and WriteStateOrDrop call the active engine error entry with code 2 on nonzero StateError.
ErrorPrelude.asm preserves the four fixed argument registers and caller stack, clears import TLS,
then tail-jumps the original error trampoline. Windows unwind metadata describes its frame.
Bind the state callbacks to ReadNativeState and WriteNativeState before publishing readiness.
Bind the active error entry and the exact verified original trampoline separately.

Test-Errors.ps1 builds an owned error entry using the recovered five-byte R9 home-store.
Ten groups cover all errors, successful returns, variadic arguments, decode-time non-local exit,
later saved-jump chaining, forwarding, suppression and native unwind.
Repeat with a new private output directory. This executes no BO3, AAE or MinHook code.
Real helper composition and captured error-chain admission remain required.

Composed real state exports and static original entries

Test-NativeComposition.ps1 pre-imports the actual helper state/error exports into a fixed owned child.
OriginalEntries.asm reproduces each exact five-byte native entry prefix, then tails imageBase+RVA+5.
The insertion thunk describes its pushed RBX in static Windows unwind metadata.
No copied native prologue is published in an unregistered runtime trampoline by this composition.
The owned image continuations validate all four prefixes and ABIs; they do not execute native game functions.

NativePlan builds checked edits from admitted image/helper ranges, export offsets and original entry bytes.
The caller supplies the complete verified count manifest and all other native code guards.
NearRelay allocates an RX block within signed rel32 reach of all four entries.
Counts, both POD bindings, relay bytes and four hooks publish through one PausedPatch transaction.
Readiness refusal restores every byte and memory protection and frees the relay before child termination.
Successful activation retains the relay for process lifetime.

Eight groups exercise 500k/1m real codec roundtrips, returned errors, decode-time non-local exit,
later error chaining, complete refusal rollback, prefix mismatch and unreachable relay rejection.
All four static original thunks and the error prelude have owned Windows virtual unwind checks.
Seven selected earlier helper cases recheck TLS, concurrency and loader/refusal contracts.
The explicit owned binding uses ZombiesOnly, 18 client-root backing records and legacy 8 roots.
The owned getter returns Zombies. This does not prove the captured game getter or client allocation.
Test-Errors.ps1 also covers all eight StateErrors and the supported-mode relaunch message.

Stock integration remains incomplete

There is no stock game profile or verified stock DLL activation route in this gate.
The 19 native count edits require compatible reader, writer, notification-key, and migration changes.
Those edits alone cannot form a game candidate.
The native helper must be active and all required game hooks must match before readiness can permit game allocation.

The supported executable calls SteamAPI_RestartAppIfNecessary with app ID 311210.
A Steam relaunch can create a game process outside this debugger's child ownership.
Do not assume a running Steam client prevents that handoff.
Normal Steam launch context, earliest allocation timing, and game debugger tolerance remain unverified.
No game launch or normal installation change forms part of this fixture.

Production helper entry

source/launch/enhanced/Helper.cpp has no fixture inputs or exports.
Its user DllMain restores temporary imports and publishes a 24-byte boot record.
The boot record identifies loader readiness. Hook activation remains a separate paused transaction.
Use Test-NativeComposition.ps1 -ProductionHelper for eleven owned Windows cases.
These cover independent boot, bad-ABI/missing-ready refusal before writes, state/error exports and rollback.
The separate owned consumer contains the fixture instrumentation.
No complete stock-game launcher or deployable expansion is included.
