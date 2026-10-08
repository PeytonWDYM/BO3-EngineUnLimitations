# Windows patcher

The patcher changes exact supported files in an existing full All-around Enhancement installation.
It also supports game-folder files listed in its public release manifest.
It includes patch code and public transform metadata. It includes no game binaries, mod assets, or extracted scripts.

The patches still need gameplay and friend compatibility validation.
The executable does not establish unlimited play or a completed stock engine fix.

## Apply or remove

1. Close Black Ops III.
2. Stop Steam downloads for the game and Workshop item.
3. Start `BO3-Engine-UnLimitations.exe`.
4. Select the full-AAE folder and game folder.
5. Select **Status** to check the installed files.
6. Select the patch files.
7. Select **Apply**.

The patcher detects Steam library folders. You can also browse to each folder.
The full-AAE Workshop item is `2631943123` under game ID `311210`.
Each selected file must match an original, current candidate, or explicitly supported earlier candidate hash.
Unsupported content stops the transaction before any target file changes.

Select **Remove** to restore the selected exact originals.
The patcher verifies each original backup before removal.
The patcher changes only the selected target files. It does not edit saves, settings, executable launch options, or Cloud settings.

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
The test result folder contains `result.json` and `test-output.txt`.
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
Scopes are `workshop` or `game`.

A transform name has the form `patchplans.module:function`.
The function receives verified canonical original bytes and a public resources path.
It returns candidate bytes. The installer checks the complete output hash before deployment.
The build bundles JSON metadata from `source/patchplans/` and the modules that package imports.
