(Note: fully vibed. Was annoyed about how easily the server instance can crash whilst playing. took me a day to do with GPT 6.1 Sol. Feel free to modify in any way)

# BO3 500K

An optional 500,000-slot server script-variable pool for Steam Black Ops III Zombies.
The launcher applies the patch in memory before the game allocates its script pool.
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

This is a test release. One manual Windows session reached Zombies and verified 500,000 usable server slots.
The client pool and actor limit retain their stock capacities.
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
The default recipe and installer still select the stock client pool.

An explicit developer build can select 250,000 usable client slots:

```powershell
pwsh -NoProfile -File scripts/release/Build-Native.ps1 -Output C:/private/bo3-client250K -DetoursRoot <Detours-v4.0.1-folder> -Python python -ExperimentalClient250K
```

Use this build only in a private game copy.
The experimental recipe checks 40 client code guards and all 19 complete count instructions before writes.
It keeps 500,000 usable server slots and includes all 61 native edits in the existing checksum transaction.
Startup receipts report the selected client capacity and required edit counts.
The release installer refuses these unapproved native payloads.

Three private Windows runs allocated the full 16,000,064-byte client pool and loaded Shadows of Evil.
One run used the explicit developer build from this source. Two runs used its preceding private prototype.
Complete free chains passed before the map, during the map, and after return to the lobby.
All three processes exited normally. Native arena checks confirmed the complete pool and fixed 65,536-bucket hash allocations.
These runs used about 40,000 live client slots. They did not stress script IDs above the stock limit.
High-ID script stress, complete native saves, companion ownership, and matching peers remain unverified.
The experimental profile does not raise the actor or player limit.

`source/patches/client_vm/exact_build_inventory.json` records the 19 client count instructions and their code guards.
The replay tools require the pinned private capture and exact-build executable used for this audit.
A new capture needs separate verification. The tools refuse other identities.
Their output must stay outside Git.

`source/tests/client-vm/Test-ClientAdmission.ps1` runs 146 refusal cases against pinned native guard spans.
It also checks the complete 61-edit recipe and both helper pool capacities in owned memory.
It requires the explicit developer build and separate private client and normalized server span files.
`source/tests/actor-pool/Test-LeafUnwind.ps1` checks the guarded leaf stubs with the Windows unwind APIs.
Both tests produce repeatable result and source-hash receipts in new output folders.

The 300-zombie goal requires more than a larger actor allocation:

| Target | Native dependency that still needs a complete patch |
| --- | --- |
| 300 actors | Inline sentient awareness tables, DObj arrays, actor iterators, save framing, and client replication |
| About 5,120 active entities | Separate normal and fake ID ranges, dependent arrays, and snapshot serializers |
| More reliable commands | Different server and client rings, an inline command arena, reset, demo, resend, and migration paths |
| More gamestate text | The 64KiB character arena, complete state copies, reset, and matching client storage |
| More clientfields | Packed set budgets, callback arrays, counter storage, schema hashes, and snapshot layouts |
| Higher rounds | Script clamps and the shared 8-bit round-completion field, plus native statistics and UI checks |
| More than 10 players | Map scripts, player state, peer behavior, and the existing 18-slot parser boundary |

A native replay proves that sentient index 104 overwrites movement data in the stock layout.
Index 299 writes beyond the stock sentient record.
Changing the actor count or relocating only the outer sentient pool cannot support 300 actors.
External awareness tables can preserve the native record stride, but their complete consumers and save format remain unverified.
`source/patches/actor_pool` prepares a disabled 300-actor and 340-sentient plan with seven storage regions.
Its 152 guarded rewrites and 95 stubs preserve the native actor and sentient record strides.
Native replays cover matrix operations, actor construction and cleanup, DObj storage, and iterator bounds.
Owned Windows tests verify stack unwinding at 352 instruction boundaries across seventeen leaf stubs.
Another owned test compares 1,829 boundaries across all 78 continuations with their original native Windows frames.
The comparison preserves five partial prologs and uses separate flattened frames for temporary stack phases.
It omits native handlers and rebases branch addresses only inside the owned fixture.
Runtime ABI admission, native handler dispatch, live registration, temporal history, combined saves, and client replication still block activation.
A separate temporal restore preparation handles 300 records in five native replay cases and five additional Windows unwind contexts.
It preserves the native loop target. The complete producer preparation passes fifteen owned replay cases.
Its temporary flags and cookie use separate storage. A count-only candidate corrupts the stack.
Eight further owned cases execute the captured history recorder, selector, producer, and restore together.
They cover actor 299, filters, empty history, ring wraps, and time clamping, with authored predicate, cookie, and relink endpoints.
The recorder keeps its eight-actor loop and handles the final four actors without overwriting the row timestamp.
These preparations stay outside the main plan. History lifetime/reset, caller buffers, save framing, whole-function unwind metadata,
native handlers, and game behavior remain unverified.
The proposed larger rewind frame also needs stack probing before allocation.
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
