# BO3 Engine UnLimitations

This project develops reversible patches for stock Steam Black Ops III with full All-around Enhancement (AAE) v3.9.5.
The goal is stable normal Zombies hosting, full-AAE mod support, and games with friends.
Friends can install the same patch when an enhancement requires matching clients.
The release targets normal Zombies, without custom game modes.

The captured co-op failure exhausted all 129,999 server script-variable slots and froze the host world.
A separate native crash occurred in AAE's custom-key Lua callback.
These failures have different captured causes.
The initiating script sequence and full game compatibility remain unresolved.

## Supported test target

| Component | Exact target |
| --- | --- |
| Client | Stock Steam Black Ops III, Windows x64 |
| Mod | Full AAE v3.9.5, Workshop item `2631943123` |
| Steam executable source | Depot `311211`, manifest `7651791086710252932` |
| Executable SHA-256 | `0B874DCC250848B7313EC13A0C76468DACC2009B5EFA2BFF4C587E169A9F77E0` |

This exact target does not include BetaLite, another AAE release, BOIII, or T7x.
An executable downgrade established the reproduction setup.
It is separate from the engine fix.
The repository contains no game executable, Workshop asset, or downgrade download.

## Patch status

| Change | Current evidence |
| --- | --- |
| Grenade-helper cleanup | Five decoded bytes changed in one weapons script. Offline checks passed. Peyton reports repeated grenade use no longer causes the failure. |
| Native Lua input guard | Missing UI context follows the existing unlock and string cleanup path. Replay, unwind, and removal checks passed. Controlled lifecycle validation remains pending. |
| Twofold War Machine fire rate | The candidate changes `fireTime` from 500 to 250 milliseconds and `lastFireTime` from 250 to 125 milliseconds. Gameplay remains unvalidated. |
| Stamin-Up sprint fire | Ordinary Stamin-Up activates the existing sprint-fire and unlimited-sprint grants across supported guns. Eligibility and native checks passed. Gameplay remains unvalidated. |
| 200 living zombies | A reviewed storage prototype remains disabled. The test package preserves the existing command cap of 64. Startup, unwind, serialization, and full consumer coverage remain unresolved. |
| Zero spawn delay | Both successful ordinary-spawn paths request zero pacing. Scheduler and pre-spawn waits remain intact. Gameplay remains unvalidated. |
| Up to three tornadoes | The offline script transform expands the Storm model pool from one to three per player. Expiry and reuse remain intact. |
| 1.5 times the split grenades | The candidate uses ceiling rounding: two children become three, and seven become eleven. Gameplay remains unvalidated. |
| 500,000 to 1,000,000 server script-variable slots | The reviewed late CRT launcher committed all 42 edits during an actual Steam launch, detached, and released BO3. BO3 then crashed during startup. The crash dump is under investigation. No expanded game pool or match is validated. Complete migration and peer tests remain pending. One million remains disabled. |

The four-file `0.1.0-test.2` package is installed for the next authorized manual test.
The deployment preserved the earlier Lua guard, 91 profile files, and the game executable.
Peyton reports that repeated grenades no longer cause the hosting failure with those candidates.
That session retained 1,408 accepted provisional samples and 219 rejected reads.
Accepted rows retained at least 18,116 free server slots and recorded no first script error.
The session has no volley markers or verified host role.
This report supports further testing. It does not prove unlimited play or isolate the effect of each candidate.

The new enhancement package still needs manual gameplay tests.
Friend joining, co-op hosting, and removal gameplay remain incomplete.
Compatibility with unpatched friends is not yet established.
Changing the pool allocation alone would leave save-state consumers inconsistent.
The release must not offer an expanded pool before its save and migration consumers have a compatible implementation.

Test manifest `0.1.0-test.3` retains the same four patch-file transformations:

| Patch ID | Target | Included changes |
| --- | --- | --- |
| `aae-core` | Workshop `core_mod.ff` | Grenade cleanup, faster War Machine, extra split children, Stamin-Up sprint fire, and `/spawn 0` |
| `aae-native` | Workshop `T7Overcharged.ff` | Native Lua input guard |
| `zero-spawn-delay` | Game `zone/zm_patch.ff` | Zero requested pacing after successful ordinary spawns |
| `storm-bow` | Game `zone/zm_castle_patch.ff` | Three Storm Bow tornadoes per player |

Manifest status `ready` means that the package has complete transform metadata.
It does not mean that all requested features or gameplay checks are complete.

The optional `zero-spawn-delay` patch works independently of AAE and round-setting writes.
While enabled, the configured delay does not affect ordinary spawns.
The normal counter path bypasses configured pacing. The positive counter path changes its 0.1-second wait to zero.
The patch preserves the scheduler's frame yield and all pre-spawn capacity and location waits.
`Wait(0)` can still yield to the scheduler. Zero requested pacing does not mean instantaneous spawns or 200 living actors.
It does not change settings on disk.
The displayed delay can remain nonzero. Custom spawn loops and special-enemy schedules remain outside this edit.
The separate AAE core change permits `/spawn 0` but does not provide this override alone.

The sprint candidate replaces the upgrade-registry predicate with the ordinary Stamin-Up perk query.
It preserves existing grant and removal wrappers, plus beast and shock eligibility checks.
It does not grant unconditional War Machine or Death Machine sprint fire.
Offline checks covered nine import bytes, eight eligibility cases, and seven native cases. Independent review passed.

## Source and evidence

All authored source and tests remain in `source/`.
Research records remain in `research/`.
Private captures, game assets, profiles, downloaded tools, and build output remain outside Git.

| Location | Purpose |
| --- | --- |
| `source/patches/grenade_cleanup/` | Exact-build candidate preparation and reversible deployment |
| `source/patcher/` and `source/patchplans/` | Windows patcher, transactions, and public transformation metadata |
| `source/patches/native_input/` | Native Lua guard preparation |
| `source/patches/gameplay/` and `source/patches/weapon_tuning/` | Exact-build script and weapon candidates |
| `source/tests/native-input/` | Instruction replay and Windows image/unwind checks |
| `source/live/` | Read-only entity and VM sampling, plus an external overlay |
| `source/reverse/` and `source/ghidra/` | Snapshot inspection and native code research |
| `source/loader/` | Runtime loader for an owned cooperative fixture |
| `source/launch/` | Separate silent-audio prototypes and owned fixtures |
| `source/launch/enhanced/` | Optional 500,000-slot Zombies launcher and exact startup admission |
| `source/launch/startup_probe/` | Separate stock-capacity API observation and owned native tests |
| `source/launch/startup_gate/` and `source/launch/late_startup/` | Cooperative CRT gate, paused native transaction, and reversible Steam transport |
| `source/tests/` | Repeatable fixture E2E harnesses |

The cooperative runtime loader cannot patch stock BO3 yet.
The startup API probe reads provisional storage at one verified caller. It does not publish larger pools.
The observation probe was removed before installing the reviewed late CRT candidate through reversible Steam launch options.
That candidate commits its native transaction, but the actual game crashes during startup. It is not ready for release.
The silent-audio prototypes do not establish quiet game startup.
Their source and limits remain documented with the investigation.

## Build the Windows patcher

The optional enhanced launcher is an experimental test candidate.
Its source, build command, and manual launch instructions are in `source/launch/enhanced/README.txt`.
It changes memory in its owned process. The patcher can configure Steam's normal Play button to start it.
The one-time setup requires Steam to be closed and saves the original BO3 launch options.
Restore Steam Play before starting other game modes or returning to stock engine capacities.
Matching enhanced clients are required to receive its expanded migration format.
Actual BO3 startup, full AAE, compressed state, and host/join compatibility remain unvalidated.
The first candidate keeps 200-zombie expansion disabled.
The patcher includes Steam Play setup only when the build bundles the optional native payload.

Use Windows x64, Python 3.12 or later, and PowerShell 7.
Run these commands from the repository root:

```powershell
pwsh -NoProfile -File scripts/release/Test-Patcher.ps1 -Output C:/private/new-patcher-tests -Python python
pwsh -NoProfile -File scripts/release/Build-Patcher.ps1 -Output C:/private/new-patcher-build -Python python
```

Select a new output folder for each command.
The build creates a private Python environment and installs the pinned dependencies in `scripts/release/requirements.txt`.
It also runs the owned-file transaction E2E.
The current suite passed 25 owned-file cases and independent recovery and link review.
The final four-file test.2 executable passed actual-stock apply and removal on private copies.
It also passed adoption of the earlier cleanup and Lua guard, then exact removal.
Independent review confirmed the packaged source, manifest, notices, and tool hashes.
The build refuses an incomplete release manifest.

The build downloads UPX 5.2.1 from its official release and verifies the archive and executable SHA-256.
Use `-UpxArchive C:/private/upx-5.2.1-win64.zip` to supply that same verified archive locally.
Use `-UpxSourceArchive C:/private/upx-5.2.1-src.tar.xz` to supply its corresponding source archive locally.
UPX unpacks the user's supported native module during patch preparation.
The build does not contain game or Workshop payloads.

Release files appear in `C:/private/new-patcher-build/dist/`:

- `BO3-Engine-UnLimitations.exe`
- `build.json`, with the executable and release-manifest hashes
- `README-patcher.md`
- `UPX-licenses/`, with license terms and the corresponding source location
- `upx-5.2.1-src.tar.xz`, the bundled tool's corresponding source archive

Publish the complete release folder so users receive the third-party notices.
Publish the matching authored source through the repository commit.
The Windows CI builds this folder and saves the owned transaction and executable test reports.
The CI uses no game or mod assets.

## Run the patcher

Start `BO3-Engine-UnLimitations.exe` to open the Windows interface.
Select the full-AAE Workshop folder and BO3 game folder.
Use **Status** to inspect supported files before a change.
Close BO3 before **Apply**, **Remove**, or **Recover**.
Keep Steam downloads stopped during a file change.

The CLI uses the same transaction engine:

```powershell
.\BO3-Engine-UnLimitations.exe status --workshop "C:/Steam/steamapps/workshop/content/311210/2631943123" --game "C:/Steam/steamapps/common/Call of Duty Black Ops III"
.\BO3-Engine-UnLimitations.exe apply --workshop "C:/private/full-AAE" --game "C:/private/BO3"
.\BO3-Engine-UnLimitations.exe remove --workshop "C:/private/full-AAE" --game "C:/private/BO3"
.\BO3-Engine-UnLimitations.exe recover --workshop "C:/private/full-AAE" --game "C:/private/BO3"
```

The patcher keeps exact originals and a transaction journal outside the selected installation folders.
The default backup folder uses `%LOCALAPPDATA%/BO3 Engine UnLimitations/` and an installation-specific ID.
Keep that folder until removal succeeds.
Use **Recover** after an interrupted transaction.
The patcher refuses recovery if another program changed a target file.

An already-patched installation needs exact originals before the patcher can adopt it.
Use `--originals C:/private/exact-originals` with files at their release-manifest relative paths.
Use `--select` with manifest patch IDs to choose a subset.
The native guard and grenade cleanup cannot repair an already-frozen match.
Read [the patcher guide](docs/patcher.md) for supported combinations and refusal behavior.
To run from source, replace the executable command with `python source/patcher/app.py`.

## Existing candidate tools

Use Python for candidate preparation and PowerShell 7 for native harnesses.
Native image checks need Visual Studio x64 C++ build tools and the Windows SDK.
The Lua replay environment needs `pefile` and Unicorn `2.1.4`.

Run these commands from the repository root with private, exact-build inputs:

```powershell
python source/patches/grenade_cleanup/Prepare-Candidate.py --source C:/private/full-AAE/core_mod.ff --output C:/private/new-cleanup
python source/patches/native_input/Prepare-LuaGuard.py --source C:/private/original.dll --profile C:/private/profile.json --output C:/private/new-guard
pwsh -NoProfile -File source/tests/native-input/Test-LuaGuard.ps1 -Python C:/private/python.exe -Original C:/private/original.dll -Candidate C:/private/new-guard/T7Overcharged.ff -Profile C:/private/profile.json -Output C:/private/new-guard-evidence
```

The Lua guard needs the inspected private unpacked image and exact-build profile.
These commands do not download originals or install candidates.
Read each tool's README before use.
Keep experimental binary changes in a separate lab copy.

## Validation and release

Follow [the release checklist](docs/release-checklist.md) before a release or gameplay claim.
Record executable identity, selected patches, mod, map, player count, and host role for each manual test.
Keep verified backups and prove exact removal before release.

Read [the capture guide](research/capture-guide.txt) for failure markers and private evidence collection.
[The investigation record](research/investigation.json) separates measured failures from hypotheses.
[The native crash record](research/native-input-crash.txt) describes the input guard's cause and limits.
[The pool audit](research/vm-pool-expansion.txt) records the unresolved save and host-migration dependencies.
