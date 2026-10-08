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

The two tracked direct lab sessions triggered Steam Auto-Cloud scans of the normal players folder.
Both scans skipped all fifteen matching files as unchanged. The lab is not a separate Cloud namespace.
At the earlier lab checkpoint, all eighty-four normal profile files matched the pre-lab baseline.
Peyton later played his normal game. Use the fresh deployment baseline for the authorized downgrade below.
Keep before/after profile and app-specific Cloud checks for future lab tests. Do not change shared Cloud settings.

On October 7, Peyton explicitly requested the author's downgrade for full AAE v3.9.5.
Steam downloaded depot 311211, manifest 7651791086710252932, through its authenticated console.
Only the normal BlackOps3.exe was replaced, after verified backups of both executables and all 91 current profile files.
The installed SHA-256 is 0B874DCC250848B7313EC13A0C76468DACC2009B5EFA2BFF4C587E169A9F77E0.
The original latest-build SHA-256 is 51CA63BBC660E0826943C60DA67606F6BCB4B3B519528B5E0548C68C9423A323.
The deployment check found no profile, other root binary, selected Workshop identity, Steam manifest or app Cloud-cache changes.
Private backups and the deployment result are in lab/backups/normal-downgrade-20261007T214527Z/.
This authorized reproduction setup is not the project's engine fix or a verified multiplayer compatibility result.
Keep experimental engine patches separate from this authorized executable downgrade.

## Agent-launched test sessions

Launch every automated or repeated game test at zero volume.
Use a bordered window at 1280 by 720 pixels.
Apply these settings in the lab copy, without changing Peyton's normal game configuration.
Mute the game rather than the system audio.

## Reported failure and current evidence

The approved full-AAE cleanup candidate remains installed in core_mod.ff for manual testing.
Peyton confirmed two marked solo volleys with the Dystopic Demolisher on Der Eisendrache.
Provisional readings remained around 72,000 to 87,000 allocated server slots. This does not validate the fix or unlimited play.
That process exited at 00:19:56 UTC on October 8 after a separate native fatal exception.
The first crash archive records a null global-context write in AAE's custom-key raw Lua callback.
Immediately before the archive, the provisional server row retained 45,547 reusable slots and no first script error.
The recursive native exceptions differ from the earlier exhausted-server failure. The UI-state lifecycle remains unresolved.
Two stopped overlays overlapped and mixed old error text with current counters. Both were closed after process identity checks.
A private native input guard passes seven instruction-emulation cases and six Windows unwind checks.
Windows maps it without executing its imports or entry. This does not prove BO3 initialization or live Lua lifecycle safety.
Native apply/removal passed on a private target. A verified original is staged for removal.
Fresh independent review covers sixteen topics with no must-fix or should-fix findings.
The native candidate has not been deployed to the normal game. Separate explicit authorization is required.
The recorder and one separately bound VM sampler/overlay waiter await the next manual full-AAE launch.
The new recorder started at 00:48:57 UTC on October 8. No agent game launch occurred.
Read research/native-input-crash.txt for the captured cause, limits, and private evidence location.

Long AAE Zombies matches can display Connection Interrupted after repeated Pack-a-Punched War Machine volleys.
Peyton reports this in solo and co-op, with failures more common in co-op.
Peyton clarified that BO3 remains open when this happens. Treat it as a match or hosting failure, not a confirmed application crash.
Whether the internal server crashes remains unconfirmed. A live process can still preserve the relevant failure state.
The initial reproduction uses stock BO3, AAE, Origins, and one or two players.

Peyton supplied the first actual failure through his normal game. That process exited when he closed it at 23:45 UTC.
Prioritize that failing-match capture over automated lab startup work. Do not launch or control another game during his session.
The earlier game process exited at 15:47 UTC. Its sampler retained 1,070 provisional rows and 110 rejected reads.
A second recorder attached another normal game at 21:34 UTC. That process exited at 21:41 UTC without a failure snapshot.
The entity sampler restored to that session retained four provisional rows before exit. The available Windows event list is empty.
The reason for the second exit remains unknown. Peyton has been asked whether he closed the game or saw a failure first.
No actual failure or volley markers were recorded in either session.
A new recorder and a separately bound waiting entity sampler were armed at 21:43 UTC.
The entity waiter was stopped before the downgraded game attached. Its exact-build profile belongs to the latest executable.
Keep both entity and VM profiles disabled for the downgraded build until its layouts are verified.
The general recorder attached Peyton's downgraded process at 21:51 UTC and verified its executable hash.
Process sampling works. Peyton confirmed a successful manual launch after the downgrade.
The saved failure contains the native AAE module from full Workshop package 2631943123.
Ctrl+Shift+F9 captured the actual failure at 22:21:20 UTC. The complete dump passed process and module identity checks.
Peyton identifies the weapon as the upgraded War Machine, Dystopic Demolisher. Both players saw Connection Interrupted.
The screenshot records Der Eisendrache, round 73, two players, and Fire Works on the weapon.
Peyton confirmed that this PC hosted the two-player match. The local server VM and entity pool are initialized in the dump.
A second read-only snapshot completed at 22:36 UTC while the same game remained open.
Both snapshots contain all 129,999 usable server script-variable slots occupied, with no free slots or reuse head.
The client VM has 25,168 reusable slots in the first snapshot. The server retained first error "Invalid opcode".
A separate formatted buffer contains "exceeded maximum number of child server script variables".
The entity pool has 148 reusable normal slots and 127 unallocated normal slots. Its allocator failure condition is false.
Server time, the complete entity pool, and the complete server VM pool match across both snapshots.
This establishes frozen host-world state and server VM exhaustion. It does not establish the initiating script or error order.
AAE detours the native engine error-handler entry. Its captured hook filters only messages with the eight-byte string VCRedist.
Other messages reach the saved native trampoline. This filter does not explain the captured script-pool error.
Saved stack code positions identify 2,079 suspended util::waittill_string helpers through the loaded export table.
The native notify setter, self accessor, entity-reference accessor, child links and string accessor verify their message and ownership fields.
Of these helpers, 1,883 wait for zombify. Player entity references zero and one own 1,768 and 115 helpers respectively.
Each helper holds a distinct tracker. Exactly 1,878 trackers have only die listeners and no returned listener.
Five trackers still have returned listeners. Six live thread records use tracker self references.
The helper locals and tracker graphs occupy 18,866 distinct pool slots. A further 3,766 notify threads refer to these helper threads.
These counts are saved footprints, not a prediction of reclaimable slots or a complete pool attribution.
Exact loaded util::waittill_any_ex code requires the caller to send die after returned to cancel its separate helper threads.
The full AAE grenade checker has outer death and player zombify cancellation, and also creates a player-owned zombify helper.
Its loaded call resolves to that exact shared helper. Raw asset and loaded script headers match.
The linker changes the call opcode and writes its parameter count from the import record. Preserve this distinction in a candidate.
The caller can end on grenade death before it cancels the separate player helper. This supports a cleanup-leak hypothesis.
Controlled producer and lifetime evidence, the first-error order, and a validated fix remain pending.
Private evidence/failure-20261007T222120Z/ retains exact-build code checks, reports, script frames and the screenshot.
Offline entity and VM layouts are checked against the captured downgraded code.
A private server-only VM profile passed a frozen-failure crosscheck against all saved pool bytes and sixteen native code ranges.
The client pool differs from the saved failure. Moving-match measurements remain provisional.
The external overlay retained 154 accepted and 163 rejected server reads before process exit.
It shows script-slot headroom, the deferred cleanup queue, call depth, first error, and sample freshness.
The overlay uses no game render hook and does not consume game input. It passed five owned native E2E modes and fresh review.
The current profile binds the exited process creation time. Rebind and verify the next process before sampling.
The older VM profile and live entity profile remain disabled.
The private full-AAE cleanup candidate changes five decoded bytes in one weapons script.
Independent extraction preserves 162 script assets, with the other 161 identical.
Captured native padding emulation, preparation guards, and fresh review passed. No gameplay or friend validation exists yet.
A separate deployment manager stages verified private backups and supports atomic apply and removal with exact hash checks.
Its private E2E restores the original asset and rejects repeated apply and damaged originals before apply and removal.
Peyton explicitly approved the reversible normal full-AAE test deployment after closing BO3.
At 23:55 UTC, only Workshop core_mod.ff changed to candidate ac4604a44d5caf093df917eb4a2a14c8979bfab0088209122125fe09304c53f8.
The exact original remains in private evidence/failure-20261007T222120Z/normal-next-match-deployment/original.ff.
All 91 profiles, 68 other full-AAE files, six game-root binaries, Steam manifest and app Cloud cache match the fresh baseline.
The new recorder and a process-bound VM/overlay waiter are armed for Peyton's manual launch.
The waiter must pass the sixteen native code hashes. A refusal requires inspection, not a bypass or guessed new addresses.
This approval covers the one AAE test asset. It does not authorize unrelated normal-game or Workshop changes.
Do not claim unlimited play or a finished stock engine patch from this candidate.
Earlier entity history remains provisional. Cross-check a saved failure snapshot before interpreting game measurements.
The 14:55 UTC F9 snapshot was a keybind test, not a reported hosting failure. Peyton requested deletion of that and old dumps.
Automatic approval review blocked both bulk and individually named deletion. No dumps were deleted. Do not analyze those test or old dumps as the next reproduction.
The previous process module inventory contains T7Overcharged.ff and AAEFreeAim.dll from Workshop item 2739657648.
Both disk files match the refreshed BetaLite lab copy. This verifies native package paths, not mapped bytes, active map identity, or War Machine availability.

The initiating cause remains unconfirmed. Server script-variable exhaustion is now measured in the actual failure.
Targeted decompilation and reverse engineering of the host state, resource allocation, cleanup, and failure paths are in scope.
Raising a verified engine limit is in scope if the patch preserves the required compatibility.
Check allocations, dependent arrays, bounds checks, and network behavior before changing a limit.
Verify reference addresses and layouts against the exact stock executable before using them.

The current recorder captures process statistics, manual markers, available logs, and manually requested memory dumps.
The offline snapshot reader measures entity pool usage with a private profile verified against the exact executable.
It separates normal, reserved, sentinel, and fake slots. It checks reuse lists, cleanup flags, and cleanup clocks.
The separate live sampler collects provisional entity rows through read-only process access and an exact private build profile.
Its native fixture E2E passed. The manual session now contains initialized game rows and retained consistency rejections. Game measurements remain unvalidated.
It rejects observed changes between repeated reads. It does not produce an atomic game snapshot.
The recorder does not yet trace projectile or GSC thread creation and deletion.
Private offline stack inspection now matches specific helper exports and verifies saved ownership through captured native accessors.
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
The new failing-match evidence above supersedes the earlier absence of a reproduction.
The producer, ownership, lifetime behavior, and first-error sequence still need verification before selecting a fix.
Read research/engine-journal.txt for the current evidence, tool checks, and lab status.

The installed BetaLite build 774 version gate matches the latest stock build string and changelist.
The author's September 30 announcement confirms current-game support and links both beta variants.
The BetaLite manifest matches Steam's latest record, dated October 2. Its separate lab copy has verified file hashes.
An older downgrade guide appeared during a lab startup exit. It does not establish that a downgrade is required.
Verify the actual selected beta package and bootstrap identity. AAE can rewrite fs_game after mod selection.
Verified BetaLite server and client paths skip an extra-weapon table. Verify the live War Machine entry before volley tests.
Built-in direct grants are diagnostic setup, not proof of physical Pack-a-Punch event or upgrade-history equivalence.
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
Its controlled abort uses a fixture-only C++ exception. Stock integration remains unimplemented.
A separate owned driver probe passed twelve memory guards, four privacy guards, one silent physical run, and fresh review.
The current default WASAPI and DirectSound routes each completed two generations, with callbacks released and CanUnload true.
All three default render routes and endpoint controls matched before and after. No audio settings changed.
The physical test used silent payloads only. It does not prove nonzero hardware suppression or device-change callback delivery.
It also does not prove factory interception, complete output coverage, or quiet BO3 startup.
Stock buffer creation returns the base DirectSound interface. Query Buffer8 before using the existing quiet factory.
One reviewed stock failure branch releases the buffer without a null check. Do not assume rejected activation allows safe stock recovery.
The separate pre-entry loader fixture passed eight native cases and fresh review using a dummy factory.
It records readiness before its imported consumer, TLS, and entrypoint. An earlier dependency call remains an explicit coverage failure.
It retains its helper until process exit through the loader dependency. It does not prove stock readiness or integrate the audio adapters.
The composed startup fixture passed nine native groups and fresh review, using owned factories and memory sinks.
It records hook readiness separately from runtime construction outside loader initialization.
Covered early DLL and TLS calls terminate the owned process before factory execution or raw publication.
This stop skips ordinary cleanup and DLL detach. It is not stock integration or graceful game recovery.
Joined worker calls, retained callbacks, recreation, and removal refusal are covered within a single-caller contract.
The earlier dependency remains uncovered. These owned-factory cases do not validate Windows interception or stock startup.
The narrow worker-start extension passed seven focused native groups across thirteen child scenarios and fresh review.
It matches both the fixed owned generic entry and full context value, while preserving real suspended creation, ID, handle, priority, and resume.
It constructs the memory runtime on ordinary worker entry before original owned setup and dispatch. Unmatched threads retain their behavior.
The target joins before its fixture entry marker. That proves marker independence, not actual EXE-entry or stock chronology.
Cold unmatched factory calls still stop. Joined callback and interface cleanup precedes runtime destruction and hook removal.
The separate SDK fixture now hooks actual CoCreateInstance, DirectSoundCreate8, and CreateThread in one transaction.
Eight memory groups across fourteen child traces passed fresh review, with fixed companion and private-output guards.
Its helper imports Windows libraries only. Accepted initialization includes two POD assignments and one compiler TLS callback.
A single silent physical SDK run completed two WASAPI first packets and Starts, then stopped on a nested DirectSound enumerator request.
The guard recorded E_PENDING and terminated before any DirectSound buffer clear or Play. Endpoint controls and defaults stayed unchanged.
This forced stop does not verify callback release, CanUnload, or graceful cleanup. No owned process remained afterward.
The next integration must address that exact original-provider request without a broad raw-object bypass.
The bounded DSOUND audit proves that request enumerates render devices and default roles, reads names, and releases local interfaces.
It uses the exact enumerator class and IID, CLSCTX_ALL, and null aggregation. Its reviewed function has no client activation.
The existing public adapter cannot serve its enumeration, property-store, and non-console requests.
Any contained forwarding must stay inside the actual saved OriginalSound call and verify the exact caller and live setup bytes.
The historical trace records module metadata only. The current disk audit is not proof of the earlier mapped bytes.
The rawPublications detector covers memory objects only. A physical zero does not establish no raw interface escape.
A separate contained-provider prototype now has eleven passing memory groups across twenty-five child traces and fresh review.
Its authority surrounds only the physical saved DirectSound factory and verifies the audited caller, arguments and live setup bytes.
Ordinary COM output storage remains unread. Only a fully qualified audited call checks its initially-null slot.
Memory rejection cases cannot prove genuine Windows admission. Positive admission, active recursion and repeated calls remain source-only.
Physical execution remains held while Peyton prepares or plays the manual reproduction.
The next quiet-start step must recover stock first-call timing and cover every output route before a game launch.
The reviewed first-factory cold-stop design records a recognized root and stops before its provider executes.
That scoped capture does not establish a completed quiet launch, gameplay, or universal output coverage.
The bounded stock coverage audit verifies known WASAPI and DirectSound routes but leaves earliest call order unresolved.
Its TLS callback and ordinary entrypoint transfer into indirect flow. Static import absence does not exclude other output routes.
The verified Sound Mix worker is registered in a dispatch table and created suspended through CreateThread, then prioritized and resumed.
Its generic thread entry performs native setup before dispatching the WASAPI worker. Both captures agree on the reviewed code ranges.
Windows defers that new thread's entry until DLL initialization completes. This does not prove that ordinary EXE entry has run.
A future initializer must match both the verified generic entry and context, preserve native setup, and run before worker dispatch.
Do not wait for an EXE-entry milestone from that gate. Independent DirectSound and earlier output timing remain unresolved.
Keep hook readiness distinct from activation-runtime readiness. Do not initialize COM or audio under the loader lock.
Pinned Detours inserts the helper before original application imports. Its own dependencies and TLS/CRT initialization still precede user DllMain.
The existing fixture's earlier provider is a helper dependency. Do not generalize that result to unrelated later BO3 imports.
The real SDK helper must avoid target, consumer, game, or mod dependencies and record actual resolved API host modules.
Inspect its final imports and initialization code. A Windows dependency is platform scope, not proof of an early output producer.
The refreshed beta PE inventory adds no proven output sink. Dynamic resolution remains a scoped gap.
The next SDK probe must keep consumer payloads silent independently of hooks, including a full DirectSound ring clear before Play.
Keep the physical SDK run held until source, guards, exact hashes, and the silence sequence have been inspected.
The assessed per-application routing alternative provides neither a verified silent endpoint nor a first-output guarantee.
Virtual endpoint names do not establish audio-discard behavior. Do not change system defaults or normal application routing for the lab.
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
