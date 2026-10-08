Enhanced Zombies launcher, experimental candidate 0.1.0-test.3

This optional launcher targets the supported downgraded Steam executable and full AAE.
It starts the normal game with a pre-imported project helper.
It does not replace BlackOps3.exe or write an app-ID file.
The patcher can configure Steam's Play button to start this helper before the game.
Restore Steam Play in the patcher to return that button to the original launch options.
The enhanced serializer supports Zombies. Restore Steam Play before starting other modes.

The first candidate uses 500,000 usable server script slots and the stock client pool.
It keeps eighteen backing client roots and imports the legacy eight-root Zombies stream.
Its migration buffer is 32 MiB. Matching enhanced peers must acknowledge the new format before receiving expanded data.
This does not prove complete host migration or compatibility with unpatched friends.
The separate gameplay patcher provides the reviewed AAE cleanup, Lua guard, and gameplay changes.
This launcher does not include or enable the unfinished 200-zombie expansion.

Build with PowerShell 7 and the supported Visual C++ x64 toolchain:
pwsh -NoProfile -File source/launch/enhanced/Build.ps1 -OutputDirectory <new-private-directory> -DetoursRoot <unchanged-official-v4.0.1-checkout> -Python <python-with-standard-library>

The output contains BO3-Enhanced-Zombies.exe, Bo3EnhancedHelper.dll, and the Detours license.
Keep the helper beside the launcher. Generated metadata and build evidence remain private.
Start Steam. Close any existing BO3 process before testing.
After the one-time Steam Play setup, use BO3's normal Play button in Steam.
Direct invocation remains available: BO3-Enhanced-Zombies.exe "<game-folder>\BlackOps3.exe" [game arguments].
Keep the launcher open until the game exits. Windows ends its owned debug child if the launcher closes.
Wait for the launcher's ready message before loading full AAE and entering Zombies.
Close the game and restore Steam Play to remove the helper from future Steam launches.

Admission and rollback

The parent locks and hashes the exact executable and helper before process creation.
Only the child's environment receives Steam app ID 311210.
The parent stops the first VM allocation and checks all decrypted native ranges.
It also requires unallocated VM, migration, and receive storage.
It verifies the helper's boot record, relocated code, unwind tables, and read-only metadata.
The Windows loader's declared IAT is the only excluded read-only range.
One paused transaction publishes nineteen capacity edits and twenty-three helper/migration edits.
Any preparation or publication refusal restores attempted bytes and page protections.
The parent frees uncommitted relay storage before terminating only its owned child.
After activation, it forwards unrelated exceptions and retains the debugger through game exit.
Private startup receipts identify the exact PID, creation time, capacities, and outcome.

Owned checks cover mapped helper admission, damaged boot/code/unwind refusal, and file identity refusal.
The VM and migration component fixtures cover native state/error behavior and reversible publication.
Those checks do not prove actual BO3 startup, AAE loading, complete compressed state, or multiplayer.
Manual solo, repeated volley, recovery, host/join, and matching-peer tests remain required before release.
