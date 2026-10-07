# BO3 Engine UnLimitations

## End goal

Deliver an optional, reversible patch for stock Steam Black Ops III that prevents the reported Zombies hosting failures.
The patched game must retain stock functionality, mod support, and the ability to play with friends.
Research and capture tools support this goal. They are not the final deliverable.

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
It does not yet measure engine entity counts, projectile cleanup, or GSC script threads.
Do not present those counters as implemented or infer an entity leak from process memory alone.

## Validation and handoff

Validate the original reproduction in solo and co-op, including repeated volleys and recovery intervals.
Validate normal mod loading and joining friends with the patch enabled.
Test both hosting and joining, including compatibility with unpatched friends.
Produce repeatable E2E evidence and record the executable, patch version, mod, map, player count, and host role.
Also verify patch removal and return to stock behavior.

Read `research/investigation.json` and `research/capture-guide.txt` for the investigation context.
Keep source in `source/` and research in `research/`.
Keep raw captures, dumps, extracted game assets, and local settings out of the public repository.
Update these instructions when evidence changes the scope or the implemented capture capabilities.
