This tool prepares a private full-AAE cleanup candidate. It does not install it.
The source must match the exact inspected full-AAE core_mod.ff hash.
Use a new output directory inside the private BO3 lab.

Prepare the candidate:
python source/patches/grenade_cleanup/Prepare-Candidate.py --source C:/path/to/full-AAE/core_mod.ff --output C:/Users/USERNAME/.codex/labs/bo3-engine/evidence/new-candidate

The candidate removes the player argument from one grenade notification helper call.
The remaining zombify helper uses the grenade as its owner.
The outer player zombify cancellation remains intact.
Two native padding instructions preserve code offsets and string relocations.
The import parameter count changes from six to five.

The decoded fastfile changes exactly five bytes.
The file size and all other decoded data remain identical.
Independent ACTS extraction retains 162 script assets with only the weapons script changed.
This result does not establish a correct game load, cleanup behavior, or friend compatibility.
It does not recover an exhausted running match or complete the stock engine-patch deliverable.

Repeat the offline preparation and extraction E2E:
python source/patches/grenade_cleanup/Verify-Candidate.py --source C:/path/to/full-AAE/core_mod.ff --acts C:/private/acts.exe --output C:/Users/USERNAME/.codex/labs/bo3-engine/evidence/new-candidate-e2e

Raw game assets and decompiled scripts remain private.
Keep the normal game and Workshop files unchanged during this experiment.

Manage-Candidate.ps1 stages verified private backups without changing the target.
Apply and Remove require BO3 closed and exact current and saved hashes.
They refuse target paths and backup paths that contain junctions or symbolic links.
They replace only the staged target. Get explicit authorization before normal Workshop deployment.

Repeat reversible deployment E2E on a private copy:
pwsh -NoProfile -File source/patches/grenade_cleanup/Test-Deployment.ps1 -Source C:/path/to/full-AAE/core_mod.ff -Candidate C:/private/candidate/core_mod.ff -OutputDirectory C:/Users/USERNAME/.codex/labs/bo3-engine/evidence/new-deployment-e2e
