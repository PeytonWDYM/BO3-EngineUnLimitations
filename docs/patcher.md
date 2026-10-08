# Windows patcher

The patcher changes exact supported files in an existing full All-around Enhancement installation.
It retains game-folder entries so older patches can be removed or recovered.
It includes patch code and public transform metadata. It includes no game binaries, mod assets, or extracted scripts.

The patches still need gameplay and friend compatibility validation.
The executable does not establish unlimited play or a completed stock engine fix.
The corrected gameplay-only `0.1.0-test.4` build bundles no engine launcher.

Test.3 can include an optional **Play enhanced Zombies** action when built with the reviewed native payload.
That experimental launcher targets 500,000 usable server slots and leaves the game executable unchanged.
Actual startup failed after all 42 edits were committed. No expanded game allocation is validated.
Direct **Play enhanced Zombies** does not change Steam launch options.
The separate **Enable Steam Play** setup changes the one Black Ops III launch field described below.
It does not enable 200 zombies. Actual startup, AAE, and multiplayer still need testing.
Keep its console open until the game exits.
After **Restore Steam Play**, normal Steam Play uses the original engine capacities.
The gameplay-only build does not include this optional action.

## Use the normal Steam Play button

The optional native build can configure Steam Play once. The patcher does not start the game during setup.

1. Exit Steam, Black Ops III, and the enhanced launcher.
2. Select the game folder in the patcher.
3. Select **Enable Steam Play**.
4. Restart Steam normally.
5. Use the normal Black Ops III **Play** button.

Steam starts the private enhanced launcher with its normal game command.
The launcher console must stay open until the game exits.
Setup preserves existing plain game arguments. An existing `%command%` wrapper stops setup.
The patcher selects the current account, or an exact automatic-login account match.
It refuses ambiguous account selection. The CLI supports an explicit userdata folder number when needed.

To remove this setup, exit Steam and the game, then select **Restore Steam Play**.
Restore changes only the original Black Ops III launch field, including whether that field was absent.
It preserves unrelated later Steam settings. It refuses restoration if you changed the installed launch options.
The private receipt is `%LOCALAPPDATA%/BO3 Engine UnLimitations/steam-play/<configuration identity>/receipt.json`.
Keep this receipt until restoration finishes. Interrupted edits recover before the next enable or restore attempt.
The public `--state` option controls fastfile backups only. It cannot change Steam receipt or locking locations.

```powershell
BO3-Engine-UnLimitations.exe steam-enable --game '<game folder>'
BO3-Engine-UnLimitations.exe steam-remove
```

For explicit selection, add `--steam '<Steam folder>' --steam-user <userdata folder number>`.
These actions change no game binary, save, gameplay setting, or Cloud setting.

## Apply or remove

1. Close Black Ops III.
2. Stop Steam downloads for the game and Workshop item.
3. Start `BO3-Engine-UnLimitations.exe`.
4. Select the full-AAE folder and game folder.
5. Select **Status** to check the installed files.
6. Select the enabled Workshop patch files.
7. Select **Apply**.

The patcher detects Steam library folders. You can also browse to each folder.
The full-AAE Workshop item is `2631943123` under game ID `311210`.
Each selected file must match an original, current candidate, or explicitly supported earlier candidate hash.
Unsupported content stops the transaction before any target file changes.

Default Apply selects `aae-core` and `aae-native`.
The `zero-spawn-delay` and `storm-bow` entries permit removal and recovery only.
Their rebuilt stock files caused a full-AAE loading regression. Restoring both exact originals allowed AAE to load.
An explicit Apply selection that includes either retired entry stops before transaction state or target files change.
Those entries remain selectable for Remove, which restores the verified originals.

Select **Remove** to restore the selected exact originals.
Default CLI removal includes all four entries, including both retired entries.
The patcher verifies each original backup before removal.
Apply and Remove change only the selected patch files. They do not edit saves, launch options, or Cloud settings.
The separate Steam Play setup changes only the selected account's Black Ops III launch field.

## Original backups

The default backup folder is `%LOCALAPPDATA%/BO3 Engine UnLimitations/<installation identity>/`.
Keep this folder until you remove every patch.
The patcher prints its exact path after each action.
Use the same selected install folders for later actions. These folders identify the backup location.

An existing patch cannot become an original backup.
If a supported earlier patch is installed, select a folder containing the exact originals.
Use the target filenames and relative paths from the release manifest in that folder.
For example, an original game asset belongs under `zone/` if its target path starts with `zone/`.
The patcher checks original hashes before it accepts an import.
It never downloads game or mod files.

## Interrupted changes

The patcher stages both before and after snapshots before the first replacement.
A durable journal records the transaction.
An ordinary failure restores the files that the patcher changed.
The patcher locks each resolved target across backup folders and selected file subsets.
An atomic shared receipt records every selected target before the first target replacement.
After forced termination, another patcher refuses those targets and reports the owning backup folder.
Use that folder with `--state` for recovery.

The shared target registry is `%LOCALAPPDATA%/BO3 Engine UnLimitations/target-coordination/`.
Keep that registry while a transaction remains pending.
The registry coordinates patchers under the same Windows account.
Concurrent changes from separate Windows accounts are outside the tested contract.
Backup and registry paths must contain no symlinks or Windows reparse points.
Private files must also have a single hard link.
The patcher resolves Steam installation junctions before it identifies each target.

If the patcher stops unexpectedly, select **Recover** before another apply or removal.
Recovery restores the transaction's before snapshots, including an interrupted removal.
It verifies every snapshot and current target before the first recovery write.
If another program changed a target, recovery refuses that content and keeps the journal.
Preserve the backup folder and inspect the changed file before recovery.

Each file replacement is atomic. A multi-file transaction can need recovery after power loss or forced termination.
Steam can replace Workshop files. Stop downloads during changes and check Status after an update.

## Command line

The same executable accepts these commands:

```powershell
.\BO3-Engine-UnLimitations.exe status --workshop 'D:\SteamLibrary\steamapps\workshop\content\311210\2631943123' --game 'D:\SteamLibrary\steamapps\common\Call of Duty Black Ops III'
.\BO3-Engine-UnLimitations.exe apply --workshop '<full-AAE folder>' --game '<game folder>'
.\BO3-Engine-UnLimitations.exe remove --workshop '<full-AAE folder>' --game '<game folder>'
.\BO3-Engine-UnLimitations.exe recover --workshop '<full-AAE folder>' --game '<game folder>'
```

Use `--select <file-id> <file-id>` to select particular patch files.
Use `--originals <folder>` to import canonical originals for an existing patched installation.
Use `--state <folder>` for an explicit backup location outside the game and Workshop folders.
Use that same state folder for later actions.

To run from source, replace the executable command with `python source/patcher/app.py`.
Install the dependencies from `scripts/release/requirements.txt` first.
Add `--resources <build folder>/resources` to use the public metadata and verified UPX tool from a completed build.

## Build and owned-file tests

Use 64-bit Python 3.12 or 3.13 and PowerShell 7 on Windows.
The build creates its own Python environment.

```powershell
pwsh -File scripts/release/Test-Patcher.ps1 -Output '<new test result folder>' -Python python
pwsh -File scripts/release/Build-Patcher.ps1 -Output '<new build folder>' -Python python
```

The build refuses an incomplete public manifest.
It runs the owned-file transaction suite before it builds the executable.
The suite needs no game files. Its cases cover paired changes, exact removal, rejected inputs, rollback, and process-death recovery.
Four retained groups cover removal-only stock entries, including recovery of older four-file transactions.
The test result folder contains `result.json` and `test-output.txt`.
It also contains enhanced and Steam logs. Owned Steam fixtures retain before/after VDF files and hash evidence.
After packaging, the build runs the executable against owned unsupported-file fixtures.
It checks CLI status, rejection, and unchanged target hashes.
These results are in `executable-tests/result.json` under the build folder.

The build downloads official UPX 5.2.1 archives and verifies pinned SHA-256 hashes.
For offline builds, supply `-UpxArchive` and `-UpxSourceArchive` with those official archives.
UPX only unpacks a verified user-supplied native module.
PyInstaller does not compress the patcher with UPX.

The `dist/` folder contains the executable, build hashes, documentation, dependency notices, and corresponding UPX source.
Distribute that folder together. Do not add local backups, transaction snapshots, or extracted game files.
The build report covers packaging. Gameplay and multiplayer results remain separate evidence.

## Public transform interface

`source/patchplans/release.json` has `schemaVersion: 1`, `status: "ready"`, and a version string.
Each entry in `features` describes one file, even if that file contains several changes.
Entries use `id`, `label`, `scope`, `relativePath`, `originalSha256`, `patchedSha256`, and `transform`.
Optional `admittedSha256` values identify supported older candidates.
Optional `applyAvailability` is `enabled` or `removal-only`. Its default is `enabled`.
This field limits new applies. It does not change removal, recovery, or original-file identity.
Scopes are `workshop` or `game`.

A transform name has the form `patchplans.module:function`.
The function receives verified canonical original bytes and a public resources path.
It returns candidate bytes. The installer checks the complete output hash before deployment.
The build bundles JSON metadata from `source/patchplans/` and the modules that package imports.
