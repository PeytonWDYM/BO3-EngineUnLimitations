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

Candidate **0.5.0-test.3** includes the actor patch in the main launcher and installer.
It applies 357 native edits and 1,079 checksum edits before game allocation.
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

This is an experimental Windows candidate. Candidate 0.4.0-test.1 loaded a Zombies map with AAE,
ended the match, and closed normally with the expanded script, callback, and counter pools.
That session used the stock actor capacity. Candidate 0.5.0-test.1 refused its first game startup before any patch writes.
Three source guards used AAE hooks or randomized padding from a later crash capture.
Candidate 0.5.0-test.2 uses the original startup instructions and complete packet function guards.
Its guards match three saved startup captures. The manual test passed startup and reached Der Eisendrache with AAE.
The client then crashed at RVA `0x49E6F2` after it read a corrupt actor index. Test.2 is not ready for play.
Test.3 moves the two remaining indexed snapshot readers with the expanded array.
Native export and reader replays cover both local clients, both snapshot slots, and all exported actors.
A new manual game test remains required.
The native actor entity allocator still has 64 dedicated slots. The actor records and packet fields are expanded,
but live populations above 64 need an allocation and cleanup repair. High-count testing is not ready.
High actor counts, save/load, host migration, matching peers, and sustained performance need game tests.

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

Expanded actor saves use a distinct format identifier. The loader accepts the guarded legacy formats,
initializes unused records, and keeps the selected read counts active until the complete native load ends.
Expanded sessions require matching patched peers; matching patches alone do not prove compatibility.

The launcher checks 886 complete actor source guards. Its 266 actor publication records share the frozen startup
transaction with the VM, clientfield, gate, and checksum patches. Failed publication restores bytes and page protections.
The primary thread registers 2,464 runtime function rows before game entry continues.
Owned Windows tests cover native frame metadata, handler translation, complete load scope, publication,
rollback, allocation ownership, and registration at three image bases. Their repeatable results stay outside Git.
These tests support candidate testing; they do not establish game or peer compatibility.

Normal entity capacity, reliable-command buffers, gamestate strings, packed clientfield budgets, round counters,
and player count retain their current limits. The patch makes no measured frame-rate claim.
A map must raise its own ordinary-zombie spawn cap to test 200–300 concurrent zombies.

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
