This experimental launcher applies one bounded native transaction for the exact downgraded Steam executable.
It uses 500,001 server records, with 500,000 usable slots, 18 client roots, and a 32 MiB migration buffer.
It preserves the 65,000-record client pool and the stock eight-root Zombies import format.

The parent creates a noninheritable kill job and assigns its suspended child before the first resume.
After the exact CRT gate becomes ready, the parent freezes that job without a debugger.
It requires exactly the original primary thread and verifies the native wait, gate, CRT, and entry-frame chain.
Two exact runtime CRT unwind records replace the encrypted disk metadata during read-only stack inspection.
Their function rows, runtime bodies, and prologues must match the verified capture; every other game frame refuses.
DbgHelp reads the stopped child through explicit memory callbacks. The receipt retains the refusal stage and reason.
It checks all 82 code guards, 19 stock counts, empty VM/migration storage, helper bindings, and 42 originals under freeze.
The parent commits both edits and relay storage before thaw, then verifies identity and gate state before release.
A refusal kills the owned child. Rollback and uncommitted relay cleanup remain under freeze.
A failure after commit keeps the relay until process exit and never rolls back resumed code.
The launcher uses no debugger attachment, debugger events, hardware-breakpoint writes, or PSS snapshots.

The parent startup budget remains 30 seconds, including the frozen transaction.
After gate release, the launcher retains its job and child until the game exits.
It has no diagnostic gameplay deadline.
The launcher writes a private FILETIME-PID-job.json receipt with startupMethod late-crt-job-freeze.
The receipt records publication stages separately and keeps liveAllocationValidated false.

Build with PowerShell 7:
  Build.ps1 -OutputDirectory <new-private-output> -VmBuild <frozen-vm-build> -GateBuild <frozen-gate-build> -DetoursRoot <pinned-detours> -Python <python>
Keep BO3-Job-Zombies.exe, Bo3EnhancedHelper.dll, Bo3StartupGate.dll, and Detours-LICENSE.md together outside the game folders.
The build locks the exact game/helper identities into the launcher and saves an import audit and source receipt.
Run directly with:
  BO3-Job-Zombies.exe <BlackOps3.exe> [game arguments]
This does not change the installed game executable or Steam configuration.

Steam setup requires the separately frozen transport profile and native review, with Steam closed.
Use the job wrapper for both setup and removal:
  python SteamSetup.py setup --native-build <frozen-native-build> --game <BlackOps3.exe> --steam <Steam-directory> --steam-user <user-id>
  python SteamSetup.py remove --steam <Steam-directory> --steam-user <user-id>
Setup uses a private cache and the canonical Steam receipt.
Removal restores the original BO3 launch field and preserves unrelated configuration bytes.

The owned E2E target uses captured inert bytes. Its test parent populates those bytes under the job freeze.
Its two caller unwind records are encrypted on disk and restored only in the owned target before its gate.
This tests the disk/runtime distinction without production metadata writes.
Its suspended process also receives LoaderThreads=1 through an exact, pinned Windows process-parameter layout.
That owned-only setup removes a persistent native worker-factory thread from the fixture before admission.
Production never writes LoaderThreads or changes loader configuration.
The fixture verifies publication, rollback, failure cleanup, deadline enforcement, and abrupt controller death after one partial edit.
These cases do not execute BO3 native code or prove game allocation.
The native freeze proof covers the recorded Windows 11 build 26200.9457.

A parent death before job assignment can leave the never-resumed child suspended.
That boundary cannot execute partial edits. Atomic job assignment during process creation is not implemented.
After assignment, last parent job-handle close kills the child, including during partial publication.

Actual BO3 startup, full AAE loading, complete migration, and hosting/joining friends remain unvalidated.
This candidate is not a finished engine patch or proof of 500,000 active game slots.
