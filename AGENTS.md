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
It separates normal, reserved, sentinel, and fake slots. It checks reuse lists, cleanup flags, and cleanup clocks.
The separate live sampler can measure entity counts through read-only process access and an exact private build profile.
Its native fixture E2E passed. Game measurements remain unvalidated.
It rejects observed changes between repeated reads. It does not produce an atomic game snapshot.
The recorder does not yet measure projectile creation and deletion or GSC script threads.
Do not label numeric entity types as projectiles without verification or infer an entity leak from process memory alone.

Current stock runtime analysis confirms a 2,048-slot allocation and a 1,022-slot normal allocator limit.
The normal allocator raises ERR_DROP with "G_Spawn: no free entities" when its range is full and its reuse list is empty.
The allocation includes separate reserved and fake ranges. Increasing one bound alone is not a verified fix.
One observed cleanup path checks a 300-millisecond clock delta before freeing flagged entities.
The same flag also marks spent split missiles. Keep the flag, numeric type, and cleanup clock separate.
Do not identify all flagged entities as cosmetic temporary events or treat that clock as projectile creation time.
Initialization clears that clock. Event helpers and native free stamp it for different purposes.
The splitter sets the flag without resetting the clock. A later collision event can refresh it.
To claim parent retention, verify one allocation lifetime and continued per-entity frames, not only advancing server time.
The native reuse version repeats after 63 complete reuse cycles. Equal external samples do not prove one lifetime.
Strict cleanup correlation needs allocation/free events, world epochs, and loss detection. That recorder remains unimplemented.
The stock packet writer and parser use 10-bit entity IDs, with 1023 as the terminator.
Do not expand normal entities into the fake range. That change would conflict with unpatched stock clients.
The verified missile type is 4. A numeric event type alone does not identify a War Machine effect.
Native split children reach a shared grenade notification producer before their anti-resplit flag is set.
The child weapon selects grenade_fire or grenade_launcher_fire. Its settings, owner, listener receipt, and actual count remain unverified.
Do not infer seven script watcher sets from an assumed seven child entities.
Native entity deletion queues cleanup of entity-owned script notification waiters and suspended stacks.
Normal VM work drains that queue. A missing grenade_dud endon alone does not establish a leak.
Some nested wait stacks can retain deferred work. Verify one entity allocation lifetime and advancing VM time before claiming failed cleanup.
The stock script-variable pools have 129,999 usable server slots and 64,999 usable client slots.
Threads share these pools. Function call depth does not count all suspended threads.
Their capacities also control lifecycle scans, notification keys, and save-state serialization. Do not patch an allocation constant alone.
The bounded review establishes no 17- or 18-bit slot ceiling. Save/migration compatibility and other consumers remain unresolved.
Private offline menu inspection verifies pool reuse chains and headroom.
The separate sampler's pure decoder agrees with that saved menu inspection. This does not validate live sampling.
A separate read-only VM sampler now has owned native fixture evidence. Game measurements remain unvalidated.
Its private game profile remains disabled. Numeric slot types do not identify script functions or grenade owners.
Its ten native E2E cases passed fresh review. The shared process API still passes all 22 entity sampler cases.
Capture the first script error and saved engine error alongside resource usage. Old or empty error buffers do not establish a cause.
These findings do not establish the cause of Peyton's reported failure. No failing Zombies match has been captured yet.
Read research/engine-journal.txt for the current evidence, tool checks, and lab status.

The installed BetaLite build 774 version gate matches the latest stock build string and changelist.
The author's September 30 announcement confirms current-game support and links both beta variants.
The BetaLite manifest matches Steam's latest record, dated October 2. Its separate lab copy has verified file hashes.
An older downgrade guide appeared during a lab startup exit. It does not establish that a downgrade is required.
Verify the actual selected beta package and bootstrap identity. AAE can rewrite fs_game after mod selection.
CoreAudio channel seeding failed the eight-channel Realtek lab case. Do not use its stereo fixture passes as proof of a quiet game launch.
The captured no-mod startup filter rejects the requested +set logo setting.
The inspected loose-file +exec route also uses restricted dispatch and does not admit that setting.
Do not bypass native command rules or treat guessed launch switches as proof of silence.
Stock directly uses WASAPI with EVENTCALLBACK and NOPERSIST. The prior helper used different stream flags.
An owned fixture with the exact native flags rejects prior zero seeding on the current default stereo endpoint before any deliberate volume reset.
The saved stereo menu format does not establish the next launch's format. Native retry can recreate the audio client.
The reviewed startup movie constructs a stock SND alias. Its lab MKV contains video only.
The native movie path submits that alias through the stock sound queue.
The stock sound worker calls the verified WASAPI submitter. The complete alias-to-samples trace remains unresolved.
Separate WASAPI and DirectSound wrappers now exist as owned-fixture prototypes.
The native baseline recorded twelve expected failures before implementation. All twelve protected scenarios passed fresh review.
DirectSound requires raw aliases to be surrendered and supported stopped secondary buffers.
An internal clear Unlock failure blocks playback and requires buffer recreation under the current contract.
They do not implement game activation or prove complete quiet startup. No game audio patch is implemented.
Separate activation adapters now preserve session-control requests, callbacks, and recreation in an owned memory-provider fixture.
Its twelve native scenarios passed fresh review, with zero raw leaf publications. It does not implement factory interception.
Shared and separate COM identities are tested. Concurrent unfinished identity construction remains untested and returns E_PENDING.
Its controlled abort uses a fixture-only C++ exception. Stock-safe stopping and real driver compatibility remain unimplemented.
Stock buffer creation returns the base DirectSound interface. Query Buffer8 before using the existing quiet factory.
One reviewed stock failure branch releases the buffer without a null check. Do not assume rejected activation allows safe stock recovery.
The separate pre-entry loader fixture passed eight native cases and fresh review using a dummy factory.
It records readiness before its imported consumer, TLS, and entrypoint. An earlier dependency call remains an explicit coverage failure.
It retains its helper until process exit through the loader dependency. It does not prove stock readiness or integrate the audio adapters.
The next quiet-start step must compose the loader and adapters, define stock-safe stopping, and verify first output coverage.
The bounded stock coverage audit verifies known WASAPI and DirectSound routes but leaves earliest call order unresolved.
Its TLS callback and ordinary entrypoint transfer into indirect flow. Static import absence does not exclude other output routes.
Keep hook readiness distinct from activation-runtime readiness. Do not initialize COM or audio under the loader lock.
Use PowerShell 7 for native harnesses that resolve directory junctions through the .NET file APIs.

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
