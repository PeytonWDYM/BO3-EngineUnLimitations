(Note: fully vibed. Was annoyed about how easily the server instance can crash whilst playing. took me a day to do with GPT 6.1 Sol. Feel free to modify in any way)

# BO3 500K

An optional engine patch for Steam Black Ops III Zombies. The Windows launcher selects these capacities:

| Pool | Capacity |
| --- | ---: |
| Server script variables | 500,000 usable slots |
| Client script variables | 250,000 usable slots |
| Actors | 500 |
| Sentients | 540 |
| Pending clientfield callbacks | 8,192 per local client |
| Clientfield counters | 8,192 records |

Candidate **0.5.0-test.9** includes the actor patch in the main launcher and installer.
It applies 710 native edits and 1,079 checksum edits before game allocation.
The installer adds a reversible Steam launch option. Original game files stay unchanged.
The actor capacity does not change a map's script spawn cap or spawn 500 zombies automatically.

## Install

1. Extract the Windows test package.
2. Close Steam and Black Ops III.
3. Start `BO3-500K-Setup.exe`.
4. Confirm the discovered game folder, or select another folder with **Browse**, then click **Install**.
5. Open Steam, select **Play**, and load Zombies.

Keep the launcher window open while playing. Closing it ends its game process.
To update an installed version, close Steam and BO3, select **Remove**, then **Install** in the new installer.
Removal restores your previous Steam launch options.

The installer reads Steam libraries and app manifests, including custom game folder names.
It supports secondary libraries, spaces, Unicode, and game folder aliases.
Command-line `install` and `status` select a game automatically when discovery finds exactly one installation.
Use `--game <folder>` to select a folder explicitly. `--steam`, `--steam-user`, and `--state` are also configurable.
No installer action starts the game.

## Compatibility and test status

This is an experimental Windows candidate. The expanded script, callback, and counter profile passed a map load, match end, and exit.
Those tests used the stock actor capacity. The separate AAE relay repair also passed a low-count Der Eisendrache session and exit.

Earlier actor candidates exposed stale snapshot, sentient, and context references. The launcher now relocates those references with their storage.
Test.6 fixed the viewmodel cache overlap at actor 64 but failed a 96-cap match at RVA `0x23F8515`.
A separate physics pool still had 83 rows. Actor 77 selected row 95 outside that allocation.
Test.7 expands the server and both client physics pools to 519 rows through their native sizing and allocation paths.
Initialization, reset, time updates, and shutdown use the same expanded count. The special row moves from 82 to 518.

Native replays cover the original fault, complete sizing constructors, actor boundaries through 499, and all revised row loops.
Windows tests cover publication, rollback, ASLR, registration, and guard refusal. These checks support game testing.

Test.7 passed a 13.5-minute Der Eisendrache control with a 96-zombie cap and advancing server frames and time.
Telemetry reached 101 allocated actors. Match end, lobby return, and normal exit passed with no new dump.

A separate 500-cap test reached 384 actors before `G_Spawn: no free entities` ended the match.
The normal entity high-water value reached its stock limit of 1,022. All three expanded physics banks remained valid.

A later Test.7 Der Eisendrache session failed a stack-cookie check.
The actor pose backup helpers visit 500 actors, but some callers still allocate a 64-actor stack object.
The saved crash frame contains position data where its stack cookie should be.
Test.8 expands the complete pose object and all six native stack frames to 500 actors.
It preserves each native exception handler, cleanup object, stack cookie, and register save.
The shared temporal caller includes both buffer expansions. New stack probes have complete unwind records.
Native replay passes with 100, 284, 300, and 500 active actors, including actor index 499.
Windows fixtures cover stack growth, normal returns, exceptions, cleanup, and stale-cookie refusal in all six frames.

The server snapshot producer also retained a separate 64-actor loop, which hid higher actors from clients.
Test.8 expands that loop, both native snapshot allocations, the staging stride, and the internal worker actor decoder together.
Native replay emits all 500 exact actor records and verifies history wrap, staging wrap, adjacent canaries, and teardown.
These checks do not prove the reported tornado failure or visibility repair in a real match.
Test.8 still needs a high-count game test, a clean exit, and a matching-peer test.

Test.9 expands the paired native actor pointer, sentient pointer, and sentient-word save-handle bounds.
Expanded reads accept 500 actor handles and 540 sentient handles. Legacy and VM-only reads retain their original 64 and 104 bounds.
Nonnull pointer fields reject encoded zero and out-of-range handles before pointer publication.
Native null fields and nullable sentient-word handles retain their original framing.
The native descriptor replay covers all three paired families, exact four-byte writes, relocated destination pools, and native returns.
Windows checks cover all six compare stubs and their complete native frames.
Whole-game high-count saves and host migration still need game tests.
Normal entities still limit the population that each map can support.
Measured 500 actors, save/load, migration, peers, and sustained performance remain required.

[Spawn pacing and actor-capacity research](research/zombie-spawn-limits.txt) describes the work needed for faster spawn batches and more than 200 zombies.
The findings include native instruction replays. Gameplay validation remains pending.

The profile accepts only Steam depot `311211`, manifest `7651791086710252932`.
The executable SHA-256 is `0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0`.
The package includes no game executable or downgrade files.
Unknown executables and changed native code refuse before patch publication.

**Linux / Proton:** unsupported in this release. Windows is the current priority.
The startup backend requires Windows job freezing. Proton needs a verified replacement backend and game tests.

## Actor patch

The actor patch expands the server pools, inline sentient awareness storage, DObj tables, and iterators together.
It preserves native record strides. Its 48MiB arena also holds snapshot, demo, history, and save/load storage.
Client actor banks use an expanded native hunk allocation. The connection ring retains 8,192 actor records per local client.
Packet, clone, entity actor-index, and demo paths use nine-bit actor IDs and matching invalid values.
Native physics banks retain 18 player rows, add 500 actor rows, and reserve one special row.
Each bank uses 5,621,808 bytes. Native hunk sizing includes the full allocation before its allocation pass.

The save wrapper marks expanded actor storage with a distinct format identifier.
The loader accepts guarded legacy formats, initializes unused records, and keeps selected read counts through the complete native load.
This does not yet establish save/load compatibility at high actor counts.
Expanded sessions require matching patched peers; matching patches alone do not prove compatibility.

The launcher checks 1,490 exact actor source guards. Its 619 actor publication records share the frozen startup
transaction with the VM, clientfield, gate, and checksum patches. Failed publication restores bytes and page protections.
The primary thread registers 2,532 runtime function rows before game entry continues.
Owned Windows tests cover native frame metadata, handler translation, complete load scope, publication,
rollback, allocation ownership, and registration at three image bases. Their repeatable results stay outside Git.
These tests support candidate testing; they do not establish game or peer compatibility.

Normal entity capacity, reliable-command buffers, gamestate strings, packed clientfield budgets, round counters,
and player count retain their current limits. The patch makes no measured frame-rate claim.
A map must raise its own ordinary-zombie spawn cap to test 200–300 concurrent zombies.

`source/patches/entity_pool` contains preparation code for a private 2,048 ordinary-entity layout.
It does not change the installed or packaged runtime.
That layout retains the two ordinary sentinel holes and moves fake entities above the ordinary range.
Its complete physical pool needs 3,072 records, with separate client-only storage and wider paired reference codecs.
Native reference-head replays do not establish a complete entity-capacity patch or game compatibility.

## Build and contribute

Use Python 3.12 or later, PowerShell 7, Windows x64, Visual Studio C++ tools, and the Windows SDK.
Use new output folders outside the repository. Keep game files, captures, and backups outside Git.

```powershell
python -m pip install --require-hashes --only-binary=:all: -r scripts/release/requirements-native.txt
pwsh -NoProfile -File scripts/release/Build-Native.ps1 -Output C:/private/bo3-native -DetoursRoot <Detours-v4.0.1-folder> -Python python
python -B source/tests/Test-Installer.py --output C:/private/bo3-installer-tests --skip-gui-tests
pwsh -NoProfile -File scripts/release/Build-Patcher.ps1 -Output C:/private/bo3-package -NativeBuild <verified-native-folder> -Python python -SkipGuiTests
```

The native builder uses official Detours v4.0.1 and generates the fixed actor profile from tracked source.
It produces an unvalidated candidate and does not change approved payload hashes in `source/release.json`.
The package builder requires those exact hashes and capacity receipts. Users do not need Python or C++ tools.
`-SkipGuiTests` keeps command-line checks and records the omitted GUI checks.
New profiles need identity, native guards, allocations, rollback, game, save, migration, and peer checks before release.
Read `AGENTS.md` before contributing.

## License and credits

Source code uses the [MIT License](LICENSE). Third-party components retain their own licenses.
Microsoft supplies [Detours](https://github.com/microsoft/Detours).
[Maurice Heumann's integrity-check research](https://momo5502.com/posts/2022-11-17-reverse-engineering-integrity-checks-in-black-ops-3/) informed the checksum work.
The release includes third-party license notices.
