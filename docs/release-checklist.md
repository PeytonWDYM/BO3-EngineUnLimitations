# Release checks

Publish the patcher source and authored tests with each executable release.
Keep game binaries, Workshop assets, backups, dumps, and private profiles outside the release archive.

## Source and artifact

1. Rebase the release branch onto the latest `main`.
2. Build the Windows executable from the reviewed commit.
3. Run the patcher transaction E2E on owned fixture files.
4. Save the transaction and frozen-executable reports with the executable SHA-256.
5. Prepare candidates from exact supported full-AAE originals in the private lab.
6. Verify candidate transforms and refusal cases against those originals.
7. Test apply, removal, and interrupted-transaction recovery on a separate copy.
8. Record the executable hash, Workshop item, patch selection, and candidate hashes.
9. Confirm the release archive contains no game or mod payloads.
10. Request a fresh review of the complete release change.
11. Resolve review findings and require passing CI before the authorized merge.

Fixture evidence proves the tested transaction behavior.
It does not prove a successful game launch or a fix for the hosting failure.
Release notes must state each incomplete gameplay check.

The current test manifest is `0.1.0-test.3`.
It lists four patch files, including the optional `zero-spawn-delay` target at `zone/zm_patch.ff`.
It includes grenade cleanup, the Lua guard, faster War Machine fire, extra split children, Stamin-Up sprint fire, zero pacing, and three Storm tornadoes.
The package preserves the zombie-limit command cap of 64.
Actual 200-actor support and expanded VM pools remain required, incomplete work.
The optional 500,000-slot launcher now has source, a checked combined build, and fresh review.
The patcher also supports optional reversible Steam Play setup.
Verify absent and empty launch fields, preserved arguments, exact account selection, and unrelated later settings.
Require Steam, BO3, and the enhanced launcher to be closed before a config edit.
Record the private original-field receipt and interrupted-edit evidence.
Keep Steam account names and IDs out of public reports.
Owned mapping tests reject damaged helper code, boot state, and unwind metadata.
Actual Steam startup, full AAE, complete compressed migration, and matching-peer tests remain open.
The 200-actor prototype remains disabled in this test candidate.
Do not mark those features complete through manifest status or fixture results.

The optional spawn patch sets requested pacing to zero after successful ordinary spawns independently of AAE and round-setting writes.
The normal counter path bypasses configured pacing. The positive counter path changes its 0.1-second wait to zero.
The patch preserves the scheduler frame yield and all pre-spawn capacity and location waits.
`Wait(0)` can still yield. Do not claim instantaneous spawns or 200 actors from this edit.
Saved settings remain unchanged. The delay setting does not affect ordinary spawns while this patch is enabled.
The displayed delay can remain nonzero. Custom spawn loops and special-enemy schedules remain outside this edit.
AAE core also permits `/spawn 0`. That command change is separate from the spawn override.

The generic patcher suite passed 25 owned-file E2E cases and current independent review.
The final four-file test.2 executable passed private stock apply and exact removal.
It also passed adoption of the earlier cleanup and Lua guard, then exact removal.
Independent package review passed. The authorized deployment preserved 91 profile files and the game executable.

The sprint candidate uses the ordinary Stamin-Up perk query instead of the upgrade-registry predicate.
It preserves existing sprint-fire and unlimited-sprint grants across supported guns, removal wrappers, and beast and shock eligibility checks.
This remains perk-dependent. It does not grant unconditional War Machine or Death Machine sprint fire.
Nine import bytes, eight eligibility cases, seven native cases, and independent review passed offline checks.
Live gameplay validation remains pending.

Peyton reports that repeated grenades no longer cause the failure with the earlier cleanup and Lua guard.
That session retained 1,408 accepted provisional samples, 219 rejected reads, and at least 18,116 free server slots.
Accepted rows recorded no first script error.
The session has no volley markers or verified host role.
Keep this manual report separate from validation of the new enhancement package.

## Manual gameplay

Use full AAE v3.9.5 from Workshop item `2631943123` and the exact executable identified in the README.
Keep a verified original backup for each changed file.
Close BO3 before apply, removal, or recovery.

1. Record the patch version, executable hash, mod version, map, player count, and host role.
2. Verify a normal launch and full-AAE mod load.
3. Verify custom-key input and map transitions after the native Lua guard.
4. Test repeated Dystopic Demolisher volleys in solo with recovery intervals.
5. Repeat the volley test while hosting a co-op match.
6. Verify that a friend with the required patch and mod versions can join the host.
7. Join a friend's lobby and complete a modded match.
8. Verify each selected gameplay enhancement against its recorded original behavior.
9. Remove the patch and verify exact original file hashes.
10. Verify a normal launch and modded match after removal.

Save repeatable markers, measurements, and failure captures in private evidence.
An unchanged error buffer or a successful short match does not prove unlimited play.
Capture the first error and process identity when a failure occurs.
Record whether each friend uses the same patch or an unpatched client.
Use matching patches when the selected features require a shared save or migration format.
Test normal Zombies without custom game modes.

Agent-launched or repeated game tests require zero game volume and a bordered 1280-by-720 window.
Apply these settings in the lab copy.
Do not change system audio, normal settings, saves, or shared Steam Cloud settings.

## Repository cleanup

Keep authored source, tests, research records, and project instructions tracked.
Use ignore rules for generated output and private evidence.
Ignore rules do not remove files that Git already tracks.

Delete an old branch only after its commits are reachable from `main`.
Verify local and remote branch tips separately.
Preserve any branch with unique commits until its owner decides its disposition.
