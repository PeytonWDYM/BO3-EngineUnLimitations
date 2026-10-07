# BO3 Engine UnLimitations

## End goal

Deliver an optional, reversible patch for stock Steam Black Ops III that prevents the reported Zombies hosting failures.
The patched game must retain stock functionality, mod support, and the ability to play with friends.
Research and capture tools support this goal. They are not the final deliverable.
Deliver a shareable Windows executable that applies and removes the validated patch.
Keep verified checkpoints committed and pushed to GitHub during the investigation.
Finish with a real pull request and a fresh review. Do not merge without Peyton's instructions.

## Required compatibility

- Preserve Peyton's existing working installation, saves, settings, and Workshop content.
- Preserve normal game launches, mod loading, and modded Zombies gameplay, including All-around Enhancement (AAE).
- The patched game must still join friends' Zombies lobbies and host games that friends can join.
- Target compatibility with friends who use unpatched stock clients, subject to the game's existing mod requirements.
- Do not assume friends must install the patch.
- Do not replace the stock client with BOIII, T7x, or another alternative client.
- Preserve existing gameplay and mod features when selecting a fix.
- Treat a patch that breaks mod loading or joining friends as incomplete, even if it prevents the reported failure.
- If a proposed fix cannot meet these requirements, explain the conflict before changing the project scope.

## Protect the working installation

Use a separate lab copy for binary changes and patch experiments.
Do not overwrite or delete files in Peyton's working installation without explicit instructions for that deployment.
Do not change its executable, DLLs, saves, settings, Steam launch options, or Workshop files during research.
Read-only inspection and external capture are allowed.
Keep experimental binaries and extracted assets inside the workspace or a clearly identified lab directory.
Design patch installation and removal so Peyton can return to the original working game.

## Agent-launched test sessions

Launch every automated or repeated game test at zero volume.
Use a bordered window at 1280 by 720 pixels.
Apply these settings in the lab copy, without changing Peyton's normal game configuration.
Mute the game rather than the system audio.

## Reported failure and current evidence

Long AAE Zombies matches can display Connection Interrupted after repeated Pack-a-Punched War Machine volleys.
Peyton reports this in solo and co-op, with failures more common in co-op.
The initial reproduction uses stock BO3, AAE, Origins, and one or two players.

The root cause remains unconfirmed. An engine limit is a hypothesis, not an established diagnosis.
Targeted decompilation and reverse engineering of the host state, resource allocation, cleanup, and failure paths are in scope.
Raising a verified engine limit is in scope if the patch preserves the required compatibility.
Check allocations, dependent arrays, bounds checks, and network behavior before changing a limit.
Verify reference addresses and layouts against the exact stock executable before using them.

The current recorder captures process statistics, manual markers, available logs, and manually requested memory dumps.
The offline snapshot reader measures entity pool usage with a private profile verified against the exact executable.
It separates normal, reserved, sentinel, and fake slots. It checks reuse lists and temporary-event ages.
The separate live sampler can measure entity counts through read-only process access and an exact private build profile.
Its native fixture E2E passed. Game measurements remain unvalidated.
It rejects observed changes between repeated reads. It does not produce an atomic game snapshot.
The recorder does not yet measure projectile creation and deletion or GSC script threads.
Do not label numeric entity types as projectiles without verification or infer an entity leak from process memory alone.

Current stock runtime analysis confirms a 2,048-slot allocation and a 1,022-slot normal allocator limit.
The normal allocator raises ERR_DROP with "G_Spawn: no free entities" when its range is full and its reuse list is empty.
The allocation includes separate reserved and fake ranges. Increasing one bound alone is not a verified fix.
The observed temporary-event cleanup path frees flagged events after their age exceeds 300 milliseconds.
The stock packet writer and parser use 10-bit entity IDs, with 1023 as the terminator.
Do not expand normal entities into the fake range. That change would conflict with unpatched stock clients.
The verified missile type is 4. A numeric event type alone does not identify a War Machine effect.
These findings do not establish the cause of Peyton's reported failure. No failing Zombies match has been captured yet.
Read research/engine-journal.txt for the current evidence, tool checks, and lab status.

## Validation and handoff

Validate the original reproduction in solo and co-op, including repeated volleys and recovery intervals.
Validate normal mod loading and joining friends with the patch enabled.
Test both hosting and joining, including compatibility with unpatched friends.
Produce repeatable E2E evidence and record the executable, patch version, mod, map, player count, and host role.
Also verify patch removal and return to stock behavior.
The current loader supports an owned cooperative native fixture. Stock BO3 does not expose that safe-point contract.
Fixture tests do not establish a working engine patch or game stability.
Do not ship a speculative byte patch as the finished fix.

Read `research/investigation.json` and `research/capture-guide.txt` for the investigation context.
Keep source in `source/` and research in `research/`.
Keep raw captures, dumps, extracted game assets, and local settings out of the public repository.
Update these instructions when evidence changes the scope or the implemented capture capabilities.
