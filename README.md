(Note: fully vibed. Was annoyed about how easily the server instance can crash whilst playing. took me a day to do with GPT 6.1 Sol. Feel free to modify in any way)

# BO3 500K

Optional 500,000 server and 250,000 client script-variable slots for Steam Black Ops III Zombies.
The launcher applies both patches in memory before the game allocates its script pools.
The installer adds a reversible Steam launch option. Original game files stay unchanged.

## Install

1. Download the Windows package from [Releases](https://github.com/PeytonWDYM/BO3-EngineUnLimitations/releases).
2. Extract the ZIP.
3. Close Steam and Black Ops III.
4. Start `BO3-500K-Setup.exe`.
5. Confirm the discovered game folder, or select another folder with **Browse**, then click **Install**.
6. Open Steam and select **Play**, then select Zombies.

Keep the launcher window open while playing. Closing it ends its game process.
To remove the patch, close Steam and the game, start the installer, and click **Remove**.
Removal restores your previous Steam launch options.

The installer reads Steam library and app manifests, including custom game folder names.
It supports secondary libraries, spaces, Unicode, and game folder aliases.
Command-line `install` and `status` select a game automatically when Steam discovery finds exactly one installation.
Use `--game <folder>` when discovery finds several installations or cannot read a manifest.
The GUI retains `--game`, `--steam`, `--steam-user`, and `--state` options.

## Compatibility

This is a test release. Private Windows sessions reached Zombies with 500,000 server and 250,000 client slots.
The actor limit retains its stock capacity while the expanded native actor patch is under development.
Expanded host migration requires matching patched clients. Matching patches alone do not prove compatibility.

[Spawn pacing and actor-capacity research](research/zombie-spawn-limits.txt) describes the work needed for faster spawn batches and more than 200 zombies.
The findings include native instruction replays. Gameplay validation remains pending.

The current profile accepts only the executable from Steam depot `311211`, manifest `7651791086710252932`.
Its SHA-256 is `0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0`.
The package includes no game executable or downgrade files.
Other versions, including future updates, require separately verified native profiles.
The installer and launcher refuse unknown versions before patch writes.
They do not reuse offsets from another game build.

**Linux / Proton:** unsupported in this release.
The startup transaction requires job freezing that [Valve's Wine backend](https://github.com/ValveSoftware/wine/blob/bleeding-edge/dlls/ntdll/unix/sync.c) does not implement.
A Proton release needs another verified startup backend and game tests.

## Build and contribute

Use Python 3.12 or later, PowerShell 7, and Windows x64.
Install Visual Studio C++ tools and the Windows SDK to rebuild the native launcher.

```powershell
python -B source/tests/Test-Installer.py --output C:/private/bo3-500k-tests
pwsh -NoProfile -File scripts/release/Build-Patcher.ps1 -Output C:/private/bo3-500k-build -NativeBuild <verified-native-folder> -Python python
```

Use new output folders outside the repository.
The setup executable contains the native launcher, both helpers, and their verified file hashes.
Users do not need Python or C++ tools.
Use `scripts/release/Build-Native.ps1` to rebuild the native files from source with official Detours v4.0.1.
New native builds need admission, rollback, startup, and peer checks before release.
Use `-SkipGuiTests` for command-line package checks when desktop interaction is unavailable.
The build receipt records that the GUI check did not run.

```powershell
python -m pip install --require-hashes --only-binary=:all: -r scripts/release/requirements-native.txt
pwsh -NoProfile -File scripts/release/Build-Native.ps1 -Output C:/private/bo3-native -DetoursRoot <Detours-v4.0.1-folder> -Python python
```

The native source build produces an unvalidated candidate. It does not update the release's approved file hashes.
Download the native developer ZIP from the test release to rebuild the installer with the approved payload.

### Further capacity work

The client VM source contains a separate save codec for 250,000 and 500,000 usable slots.
It preserves the stock client codec at 65,000 total slots and isolates client import state from server import state.
The expanded client format uses its own identifier and contains no server player-root records.
Captured native allocation and slot-codec replays exercise the larger capacities in owned memory.
These checks do not establish game, save, peer, or migration compatibility.
The default recipe and installer select 250,000 usable client slots.
The recipe checks 40 client code guards and all 19 complete count instructions before writes.
It keeps 500,000 usable server slots and includes all 61 native edits in the existing checksum transaction.
Startup receipts report the selected client capacity and required edit counts.
The release installer checks the exact default payload hashes before staging these native files.

Three private Windows runs allocated the full 16,000,064-byte client pool and loaded Shadows of Evil.
One run used the integrated client250K recipe. Two runs used its preceding private prototype.
Complete free chains passed before the map, during the map, and after return to the lobby.
All three processes exited normally. Native arena checks confirmed the complete pool and fixed 65,536-bucket hash allocations.
These runs used about 40,000 live client slots. They did not stress script IDs above the stock limit.
High-ID script stress, complete native saves, companion ownership, and matching peers remain unverified.
The client250K profile does not raise the actor or player limit.

`source/patches/client_vm/exact_build_inventory.json` records the 19 client count instructions and their code guards.
The replay tools require the pinned private capture and exact-build executable used for this audit.
A new capture needs separate verification. The tools refuse other identities.
Their output must stay outside Git.

`source/tests/client-vm/Test-ClientAdmission.ps1` runs 146 refusal cases against pinned native guard spans.
It also checks the complete 61-edit recipe and both helper pool capacities in owned memory.
It requires the default native build and separate private client and normalized server span files.
`source/tests/actor-pool/Test-LeafUnwind.ps1` checks the guarded leaf stubs with the Windows unwind APIs.
Both tests produce repeatable result and source-hash receipts in new output folders.

The 500-actor target requires coordinated native storage, codecs, and script limits:

| Target | Native dependency that still needs a complete patch |
| --- | --- |
| 500 actors | Inline sentient awareness tables, DObj arrays, actor iterators, save framing, and client replication |
| About 5,120 active entities | Separate normal and fake ID ranges, dependent arrays, and snapshot serializers |
| More reliable commands | Different server and client rings, an inline command arena, reset, demo, resend, and migration paths |
| More gamestate text | The 64KiB character arena, complete state copies, reset, and matching client storage |
| More clientfields | Packed set budgets, callback arrays, counter storage, schema hashes, and snapshot layouts |
| Higher rounds | Script clamps and the shared 8-bit round-completion field, plus native statistics and UI checks |
| Stable future sessions with 10 players | Host load, map scripts, player state, and matching-peer stress tests |

A native replay proves that sentient index 104 overwrites movement data in the stock layout.
Index 299 writes beyond the stock sentient record.
Changing the actor count or relocating only the outer sentient pool cannot support 300 actors.
External awareness tables can preserve the native record stride, but their complete consumers and save format remain unverified.
`source/patches/actor_pool` defaults its export to 500 actors and 540 sentients with seven storage regions.
The earlier 300/340 shape remains available for owned comparisons.
The target uses 33,932,440 storage bytes and passes native replays at actor 499 and sentient 539.
Its 152 guarded rewrites and 95 stubs preserve the native actor and sentient record strides.
Native replays cover matrix operations, actor construction and cleanup, DObj storage, and iterator bounds.
Owned Windows tests verify stack unwinding at 352 instruction boundaries across seventeen leaf stubs.
Another owned test compares 1,829 boundaries across all 78 continuations with their original native Windows frames.
The comparison preserves five partial prologs and uses separate flattened frames for temporary stack phases.
It omits native handlers and rebases branch addresses only inside the owned fixture.
Runtime ABI admission, native handler dispatch, live registration, temporal history, combined saves, and client replication still block activation.
The 500-actor replays also pass 500 constructors and cleanup calls, DObj storage, iterators, admission scans, history, and the full no-fire caller.
Complete producer/rewind frame tests pass 739 Windows instruction contexts for each expanded shape.
The tests refuse stale allocation and register-save metadata. Live native handler bindings remain under development.
A separate temporal restore preparation handles 300 records in five native replay cases and five additional Windows unwind contexts.
It preserves the native loop target. The complete producer preparation passes fifteen owned replay cases.
Its temporary flags and cookie use separate storage. A count-only candidate corrupts the stack.
Eight further owned cases execute the captured history recorder, selector, producer, and restore together.
They cover actor 299, filters, empty history, ring wraps, and time clamping, with authored predicate, cookie, and relink endpoints.
The recorder keeps its eight-actor loop and handles the final four actors without overwriting the row timestamp.
These preparations stay outside the main plan. History lifetime/reset, complete caller coverage, save framing, whole-function unwind metadata,
native handlers, and game behavior remain unverified.
The separate rewind preparation expands its temporary buffers and calls the guarded native stack probe before allocation.
Five further owned cases cover rewind, restore, filters, time clamping, and refusal of a missing probe.
The probe also executes on three owned Windows threads with real stack growth and complete function-table cleanup.
These helper tests do not admit the relocated game frame or its handlers.
A separate caller preparation moves the adjacent corpse buffer and expands the frame to 21,728 bytes.
Three complete no-fire caller replays verify stock64, prepared300, and refusal of an old corpse-buffer address.
They preserve current poses, cookies, home-space arguments, saved registers, and separate 64-corpse storage.
Corpse and external helper endpoints are authored. Firing paths and live behavior remain unverified.
The caller metadata preparation moves its allocation, eleven register saves, and cookie word together.
Owned Windows tests pass all 748 caller instruction-boundary contexts and reject both stale-metadata candidates.
Two normal returns and two real C++ exceptions also pass through captured native cookie handlers in an owned fixture.
Each exception runs its captured cleanup leaf once. The stale cookie word triggers the expected refusal.
The body, language CRT, cookie check, and destructor endpoints are authored. The game's CRT path remains unverified.
Direct cookie-handler replay passes 108 cases and rejects sixty incomplete frame-translation candidates.
Temporary stack phases need the original native frame address for both cookie lookup and decode.
The direct replay supplies that address as an argument.
A separate bridge prototype passes owned Windows exception tests at temporary depths 8, 16, 24, 32, and 40.
Each depth covers stock and expanded frames, normal return, cleanup, outer catch, and native prolog handler suppression.
Missing frame translation fails the cookie check. An untranslated stub code location skips C++ cleanup and triggers refusal.
The prototype remains outside game registration. All native owners, the game CRT, catch blocks, and collided unwind remain unverified.
The existing plan's twenty handler sites use one GS-only handler across twelve native frame owners.
Prepared recipes now guard both helper bodies and complete root metadata, including cookie words. Fifteen altered-owner or metadata cases refuse output.
No 300-actor, expanded-entity, network-capacity, higher-round, or player-count patch is active here.
No new engine performance claim applies to this source work.

## License

This project's source code uses the [MIT License](LICENSE).
You can use, modify, distribute, and sell it. Keep the copyright and license notice with copies.
Third-party components retain their own licenses.

## Credits

Microsoft supplies [Detours](https://github.com/microsoft/Detours).
[Maurice Heumann's integrity-check research](https://momo5502.com/posts/2022-11-17-reverse-engineering-integrity-checks-in-black-ops-3/) informed the checksum work.
The release includes third-party license notices.
