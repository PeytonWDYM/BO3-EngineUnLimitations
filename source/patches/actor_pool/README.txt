500 ACTOR / 540 SENTIENT NATIVE PROFILE

runtime_recipe.py composes the active Windows profile from these guarded components.
The native launcher publishes the complete profile before game allocation.
The installer selects that launcher through a reversible Steam launch option.
Read the repository README for the current candidate and game-test status.

PreparedTablePlan.require_activation() still refuses the incomplete standalone table export.
That restriction does not describe the complete runtime recipe used by the launcher.
The following notes preserve the earlier isolated preparation and its test boundaries.

HISTORICAL PREPARATION NOTES

shape.py supplies every emitted capacity and storage extent.
The forty extra sentients preserve the stock count difference. Actual demand remains unmeasured.
Native actor records retain stride 0x2110. Native sentient records retain stride 0x3088.
The target matrices contain 540-by-540 entries of 72 bytes and two bytes.
Storage includes actors, secondary actors, sentients, both matrices, handle heads, and DObj pointers.
The seven target regions use 33,932,440 bytes. Stub storage and allocator overhead are additional.
The earlier 300/340 shape remains available for comparisons. It uses 16,165,640 bytes.
Prepare-ActorPlan.py defaults to 500 actors. Use --actors 300 to export the earlier shape.
Replay storage reserves thirty-two MiB between the knowledge matrix and actor storage.
The old sixteen-MiB spacing overlaps at 540 sentients and fails admission.
The shared 2,047-node handle pool, corpse pool, and normal entity limit retain their stock sizes.

table_plan.py prepares 152 guarded edits and 95 stubs.
The direct member inventory includes 75 sites. These operations preserve the native record layout.
omissions.py adds the DObj relocation, three signed iterator bounds, and the live actor scan.
The DObj setup also uses its old base as another array's end.
A separate guarded stub restores that boundary before the unrelated six-entry loop.
actor_omissions.json records all twelve original omissions and this additional dependency.
The sentinel 64 and temporal actor-state storage remain unchanged and block activation.

Admission requires both the exact executable SHA-256 and the pinned capture-manifest SHA-256.
Every accessed capture range and native instruction has its own hash guard.
The admitted executable SHA-256 is:
0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0
The private capture uses timestamp 1765634846 and imageSize 494186496.
A matching timestamp alone cannot admit another executable or capture.

Prepare-ActorPlan.py exports bytes only into a new private BO3 lab directory.
Its addresses describe owned replay allocations against an unpacked module.
They are not runtime allocation addresses or packed-file offsets.

python -B source/patches/actor_pool/Prepare-ActorPlan.py --module <pinned-module.json> --executable <exact-private-executable> --output <new-private-lab-directory> --actors 500

Write failure cases before logic. source/tests/actor-pool/failure-cases.txt records this change's cases.
Run each test with a new result path inside the private BO3 lab.
The native replay tests need the local Capstone and Unicorn dependency directories.

python -B source/tests/actor-pool/Test-ExternalSentientTable.py --module <pinned-module.json> --executable <exact-private-executable> --dependencies <unicorn-directory> --output <new-private-result.json>
python -B source/tests/actor-pool/Test-ActorStorageOmissions.py --module <pinned-module.json> --executable <exact-private-executable> --dependencies <unicorn-directory> --output <new-private-result.json>
python -B source/tests/actor-pool/Test-ActorPlanAdmission.py --module <pinned-module.json> --executable <exact-private-executable> --output <new-private-lab-directory>

The matrix replay checks 450 direct-instruction states, 36 accessor pairs, allocation bounds, and real CRT construction and cleanup.
The storage replay checks 11 groups, including actor 299 DObj reads, 300 DObj entries, and the unchanged adjacent array.
The admission replay checks 13 refusals. Results include source and capture hashes.
Callback stand-ins and stop boundaries appear in each replay result.
These tests do not execute game startup, native save framing, Windows exception unwinding, or matching peers.

PreparedTablePlan.require_activation() always refuses activation.
ACTIVATION_GATES lists the exact remaining requirements.
Actor-state stack arrays at rsp+0x40, +0x340, and +0x640 cannot accept a larger count alone.
The temporal path also needs complete output, history storage, and caller expansion.
This temporal state path has no stream writer. Save framing is a separate requirement.
temporal_layout.py derives the two vector arrays, validity flags, and twenty-row history extent from ActorShape.
The 300-actor output contains 7,500 bytes. Each history row contains 7,804 bytes.
temporal_restore.py prepares four guarded edits and one stub for the native restore function.
It keeps the native loop-back compare in place and preserves the native record stride.
Test-TemporalRestore.py checks stock64, rejected count-only300, boundary indices, all-valid, and none-valid cases.
The relink endpoint is an authored callback. Vector bits, invalid records, flags, stack, and nonvolatile registers are checked.
This restore preparation stays outside table_plan.py until its caller buffers, history storage, and saves match.
temporal_producer.py relocates the complete guarded producer with two 300-byte flag arrays.
Its 744-byte frame preserves the native cookie and saved registers without requiring a page-sized allocation.
relocate_function.py widens local branches and displacements and rebases native calls and RIP operands.
Test-TemporalProducer.py checks fifteen cases, including stock64, row fallbacks, filtering, and boundary indices.
Its selector, predicate, and cookie endpoints are authored callbacks. A count-only candidate corrupts its stack.
temporal_history.py prepares the native twenty-row recorder and selector for separate 156,080-byte storage.
It preserves the native eight-actor loop and exits after four lanes in the final group.
An unchecked final group overwrites the row timestamp with four extra validity bytes.
Test-TemporalHistory.py runs eight complete recording, selection, interpolation, and restore cases.
The tests cover actor 299, empty history, filtering, ring wraps, large counters, and selector time clamping.
Only the predicate, cookie, and relink endpoints are authored in this combined replay.
Both temporal preparations stay outside the main plan. History construction/reset, complete caller coverage, save framing,
whole-function Windows unwind metadata, native handlers, and actual game behavior remain unverified.
temporal_rewind.py prepares the complete rewind with a 7,624-byte frame and a guarded probe before allocation.
It expands all temporary buffers, validity flags, output offsets, cookie, and saved-register addresses.
Test-TemporalHistory.py --include-rewind adds five cases to the eight-case history replay.
They exercise rewind and restore, filters, the short-history exit, time clamping, and a rejected missing-probe candidate.
The captured probe executes against an owned thread-information block. This replay cannot test real guard-page faults.
Test-StackProbe.ps1 also executes the complete guarded probe on three new Windows threads.
Authored wrappers allocate 7,624, 15,824, and 21,728 bytes after the probe.
Actual stack limits and committed pages match each allocation. All owned function tables are deleted.
These wrappers do not execute the relocated game rewind or verify its complete Windows frame and handlers.
temporal_caller.py prepares 22 guarded edits to the complete owning caller.
It keeps the actor buffer start, moves the adjacent corpse buffer, and expands the frame to 21,728 bytes.
Corpse capacity remains 64. Absolute home-space argument and saved-register addresses remain unchanged.
Test-TemporalCaller.py executes the complete no-fire caller with native temporal functions and probing in three owned cases.
Stock64 and prepared300 restore current poses. Retaining the old corpse address corrupts actor restoration and fails the test contract.
Cookies, home-space arguments, return stack, saved GPR/XMM registers, and corpse markers match.
Corpse and external helper endpoints are authored. Firing paths and live behavior remain gated.
caller_unwind.py guards the complete native metadata, C++ function-info, state map, cleanup map, and cleanup leaf.
It moves the allocation, eleven explicit register saves, and cookie word. Native handler flags remain unchanged.
The low-frame cleanup object and helper offsets remain unchanged. In-place instruction sizes preserve all language state boundaries.
Test-CallerUnwind.ps1 checks all 748 stock and expanded instruction-boundary contexts through actual Windows virtual unwinding.
It rejects unchanged allocation and unchanged save-offset metadata. Every owned registration is deleted.
The fixture executes the prolog and epilog in an emulator. Body contexts reuse the complete frame. Windows handlers are omitted.
Test-CallerException.ps1 executes both captured prologs and epilogs on Windows with an authored body and fixture CRT.
Two normal returns and two real exceptions pass. Captured native cookie handlers preserve all six cookie checks.
Each exception runs the captured cleanup leaf once and reaches the outer catch. A stale cookie word exits with refusal code 23.
All eight function records are deleted and both owned code allocations are released on success.
The language CRT, body, cookie check, and destructor endpoints are authored. The game CRT and real firing paths remain unverified.
ActorNum has a six-bit netfield. clonedFromActorNum has seven bits and stores source-index-plus-one.
The separate actor packet number codec also uses six-bit absolute indices.
These client and peer contracts need complete expansion before actor 299 can replicate correctly.
Save framing must preserve legacy 64/104/64 imports and admit a distinct expanded format.
codec_contract.json defines that requirement. It does not implement the format.

unwind.py exports exact native frame owners, their guarded unwind metadata, and each stub's stack transitions.
It proposes ALLOC_SMALL 16 for the leaf accessor.
The inventory identifies 78 native frame continuations and 16 sites in twelve verified native leaf functions.
Leaf admission checks full instruction bodies, register aliases, vector state, stack use, and return contracts.
leaf_unwind.py describes every instruction boundary in those sixteen stubs and the leaf accessor.
Test-LeafUnwind.ps1 registers these seventeen stubs in owned Windows allocations.
It verifies 352 instruction-boundary contexts with RtlLookupFunctionEntry and RtlVirtualUnwind.
Twelve wrong stack-phase mutations fail. Every owned function table is deleted after its test.
This does not register a game patch or verify native handler dispatch.
native_unwind.py reads complete native chains and selects the saves active at each hook.
continuation_unwind.py prepares complete flattened frames with temporary allocation and save offsets.
Test-NativeUnwind.ps1 compares 1,829 boundaries across all 78 continuations with the original Windows frames.
It checks all native caller GPR and XMM values, including five hooks inside native prologs.
The original frame uses captured native unwind bytes. Only owned chain addresses and handler flags change.
The owned stub copies rebase branch addresses. The emitted game-plan bytes remain unchanged.
Each phase chains to a separate complete frame with the logical native procedure bounds.
This prevents Windows from treating the continuation jump as a function exit.
The comparison refuses 1,642 missing-depth, 78 missing-allocation, and 66 wrong-save mutations.
All owned registrations are deleted. The fixture never executes the stubs or game code.
Unscaled XMM offsets at odd eight-byte phases still need runtime ABI admission.
Native handler dispatch and game registration remain unverified.
Test-HandlerCookie.py directly replays the captured cookie handler and its common helper in 108 cases.
It rejects sixty untranslated-frame and shifted-offset-only candidates at nonzero temporary stack depth.
The handler uses the native frame address for both cookie lookup and XOR decoding.
A runtime bridge must preserve that address. Moving the cookie offset alone does not preserve the decode.
The test supplies the translated address directly and authors the dispatcher, frame header, and final cookie check.
That direct replay does not implement a bridge or verify Windows exception dispatch.
handler_bridge.hpp provides a separate disabled runtime-binding prototype.
It translates the fixed frame, code location, native function entry, image base, handler, and language data together.
It keeps the Windows context pointer shared, forwards scope updates, and suppresses handlers inside the original incomplete prolog.
Test-CallerException.ps1 -TemporaryStack <8|16|24|32|40> throws from a separate owned stub outside the native language state map.
At each depth, stock and expanded frames pass normal returns, cleanup once, outer catch, and handler suppression.
The five runs exercise thirty cookie checks, ten cleanup calls, and twenty translated handler calls.
Suppression runs skip all twenty native handler calls. Missing frame and code-location translations fail at each depth.
Odd eight-byte depths use unscaled XMM save offsets and an adapter that preserves call alignment.
Every successful run deletes eighteen function records and releases both owned code allocations.
The prototype does not bind game handlers. The game CRT, native catches, collided unwind, and all owner-specific frame phases remain unverified.
native_handlers.py guards the native GS-only handler, common helper, and twelve complete root metadata records including their cookie words.
These roots cover all twenty handler sites in the existing continuation plan. The separate C++ temporal caller has a different contract.
unwind.py exports each prepared root, prolog, image base, cookie offset, and handler-data address with runtime binding disabled.
The native unwind export rejects an unknown owner, both changed helper bodies, and all twelve changed cookie words.
Its 79-continuation Windows comparison still passes 1,834 contexts and 1,788 metadata refusals.
The emitted actor-plan bytes remain unchanged. Prepared recipes do not establish actual owner-specific exception behavior.
Test-NativeUnwind.ps1 -IncludeTemporalRestore adds the separate restore stub to the owned comparison.
That run covers 79 continuations and 1,834 boundaries. The restore adds five contexts without temporary stack allocation.
Continuation metadata must preserve the complete native frame and describe added stack phases.
Grouped CHAININFO alone cannot describe an added fixed allocation that differs from the primary frame.
Native handlers, partial prologs, epilogs, and game registration remain activation gates.
Startup must allocate, construct, guard, and roll back all storage before the first native consumer.
Complete consumer coverage, shared handle demand, save behavior, and actual Windows game behavior remain open.

The external-table, storage-omission, history, caller, and admission replays accept --actors 500.
These runs check actor 499 and sentient 539, all 500 constructors and cleanup calls, and the complete temporal chain.
The native history contains twenty 13,004-byte rows at the target shape.
The producer allocates 1,160 stack bytes. Rewind allocates 12,632 bytes. The caller allocates 26,736 bytes.
temporal_unwind.py guards all six producer/rewind runtime fragments and their complete chained metadata.
It maps runtime boundaries and operation offsets to the relocated instructions.
Allocation, late register saves, cookie offsets, and chained parents use the selected shape.
Test-TemporalUnwind.ps1 checks 739 actual Windows unwind contexts at both 300 and 500 actors.
Both shapes refuse two stale allocations and two stale register-save tables. All four owned function tables are deleted.
The fixture executes native prologs, late saves, and epilogs. Other body contexts use the active frame state.
It omits handlers for the owned comparison and authors the final cookie-check endpoint.
This closes the owned frame comparison. Live registration, native handler execution, saves, and client replication remain separate requirements.

Test-NativeUnwind.ps1, Test-LeafUnwind.ps1, and Test-CallerException.ps1 accept -Actors 300 or -Actors 500.
The Python export commands accept the corresponding --actors option. Their default remains 300 for earlier comparisons.
At 500, the complete continuation comparison passes 1,834 contexts across 79 continuations with -IncludeTemporalRestore.
It refuses 1,642 wrong-depth, 79 missing-allocation, and 67 wrong-save candidates.
The leaf comparison passes 352 contexts across 17 stubs and refuses twelve incorrect stack-phase candidates.
The caller exception test uses the complete 26,736-byte frame at depths 0, 8, 16, 24, 32, and 40.
Each run passes two normal returns, two C++ exceptions, six cookie checks, and two cleanup calls.
Each run refuses a stale cookie. Bridge depths also refuse missing frame translation and incorrect native code locations.
Suppression runs preserve the native incomplete-prolog rule. Successful runs release all owned function records and code allocations.
Actual game CRT, all native owners, and live registration remain unverified.

temporal_save.py prepares the complete actor-history writer section without changing the owning frame.
It retains the stream call at native RVA 0x1166C3 and preserves RBX for the following stock corpse-history section.
The expanded write uses 156,080 bytes at 300 actors and 260,080 bytes at 500 actors, followed by the unchanged counter.
The legacy importer consumes exactly 33,360 bytes and preserves all twenty stock rows, including raw vector and timestamp bits.
It initializes every unused actor and preserves the following input section.
Internal HistoryFormat values require separately admitted root context. They are not assigned save identifiers.
Test-TemporalSave.py checks twelve native section/write/import cases, eight import refusals, and six address/guard refusals.
The native stock writer runs both aligned and unaligned inline copies and the near-full general write path.
The prepared writer uses an authored stream endpoint. Native compression, root header binding, complete attachments, and game saves remain unverified.
These save preparations remain outside table_plan.py and the default launcher.

temporal_reset.py preserves the complete 0x23A10-byte native level clear and adds the selected external history clear.
The called stub returns the original level address and uses an independent 40-byte frame.
Its ALLOC_SMALL40 metadata describes that independent frame.
Test-HistoryReset.py checks six stock, expanded, and rejected stale-extent cases with two resets each.
Both expanded shapes clear the complete history, preserve allocation canaries, and retain nonvolatile registers and stack alignment.
Ten altered-guard, invalid-address, overlap, and reach refusals pass. The memset endpoint is authored.
The direct reference audit identifies the original level reset. Computed reset consumers and actual map transitions remain unverified.

static_frames.py emits the independent reset stub in an owned DLL with static PE unwind data.
Test-StaticFrames.ps1 checks actual Windows lookup and unwinding at all nine instruction boundaries.
Both shapes pass two complete owned resets, buffer canaries, call order, return value, and lookup removal after DLL unload.
Four unsupported template shapes and two changed-template/missing-binding cases refuse output or code writes.
The complete instruction shape must match its admitted unwind metadata.
The fixture uses authored clear endpoints and owned buffers. It makes no dynamic function-table registrations.
This closes the owned called-reset frame test. Complete actor continuations, game handlers, and live binding remain required.

actor_wire.py prepares five coordinated nine-bit actor packet and entity actor-index changes.
The absolute removal writer, live-record writer, and client reader keep their original instruction sizes and call locations.
Both named entity actor-index descriptors expand to nine bits, including room for the selected clone sentinel.
The preparation guards the complete codec span, actor parser, class-three table, native field list, and named descriptors.
Prepare-ActorPlan.py exports these five changes separately under wirePreparation. They remain outside activation.
Test-ActorWire.py passes 61 native packet/field cases and thirteen guard refusals for each expanded shape.
It round-trips all 500 records in reverse order through the captured actor writer, patched client number-reader call site, and actor payload reader.
It verifies changes, forced unchanged records, omitted unchanged records, sparse removals, field payloads, padding, canaries, cookies, and nonvolatile registers.
Both entity actor-index fields pass their captured generic field codecs at sparse boundaries and the selected clone sentinel.
Stock high-ID packets and a mismatched six-bit reader fail the comparison. Consecutive IDs alone can hide that truncation.
The clear, alternate field-table flag, and cookie endpoints are authored. Unicorn executes the captured codec bodies and stock class-three field selection.
Expanded snapshot copies, client caches, sentinel consumers, demo/migration framing, alternate field selection, and real peer admission remain required.

client_snapshots.py prepares complete external snapshot storage for two local clients, with two slots per client.
Each snapshot retains all native member offsets and appends the expanded 80-byte actor array after the complete stock snapshot.
Five guarded rewrites coordinate the actor clamp, exporter/consumer offsets, and two native slot-selection stubs.
The stubs preserve the native client object layout, sequence increment, call arguments, and internal retry entry.
Prepare-ActorPlan.py exports the storage, five edits, two stubs, and complete frame requirements under clientSnapshotPreparation.

The 500-actor shape needs 618,592 bytes per snapshot and 2,474,368 bytes for all four snapshots.
The 300-actor shape needs 602,592 bytes per snapshot and 2,410,368 bytes for all four snapshots.
Test-ClientSnapshots.py passes 27 cases for 500 actors and 26 for 300 actors, with eleven owner and six address refusals each.
The captured copy loop preserves every native record byte across the connection ring boundary.
The captured client address calculation reaches every exported record. Complete snapshot and client-object canaries remain intact.
The comparison detects stock truncation and metadata corruption from a count-only patch.

Test-NativeUnwind.ps1 -ClientSnapshots compares both stubs with their complete original native frames.
Both shapes pass nine Windows instruction boundaries and four incorrect native allocation/save metadata comparisons.
Runtime registrations disappear after the owned comparison. The actual game performs no writes in these tests.
Complete native caller execution, all snapshot reset/copy paths, connection ring allocation, client actor storage, saves, and real peers remain required.
These snapshots stay outside activation and the default installer recipe.

demo_writer.py prepares the complete writer frame and separate prior-record allocation for either supported actor shape.
The expanded temporary ID list moves the native allocation, three register-save offsets, cookie save/read/data, and epilogue together.
Its scan block uses an ordinary call and conditional branch. A direct jump at the comparison failed Windows epilogue detection.
The called leaf compares EAX and reads the following native prior count only when the scan finishes.
demo_reader.py coordinates the separate six-bit ID reader, forty stores through their shared base, and complete prior-record reset.
Its fixed-width edits retain both native frames. The writer uses dense prior records; playback uses actor-ID-indexed records.
Prepare-ActorPlan.py exports all eleven changes, complete storage, writer frame data, and a separate called-leaf frame with runtime binding false.
The combined plan checks 221 native edits, 101 bodies, and ten complete storage regions without overlaps.

Test-DemoWriter.py executes six complete native writer frames per shape and verifies native framing/parser output, complete copied records, and preserved frames.
It includes removals, sparse updates, unchanged lists, an empty list, and refill. A count-only frame loses its native cookie.
Ten writer/metadata guards and eight invalid code/storage intervals refuse preparation.
The packet artifact contains actual writer packets and separate authored source records for repeatable playback comparison.
Test-DemoReader.py consumes that artifact through the complete native reset, playback, and rebroadcast paths for demo modes zero and two.
Twelve frames per shape preserve complete ring/prior-record storage, following counts/cursors, native scratch arrays, and canaries.
Every rebroadcast packet matches its input byte for byte. Stock ID width or record storage fails playback.
Nine reader/reset owner and metadata refusals plus five invalid complete storage intervals pass.

Test-CallerUnwind.ps1 -DemoWriter -Actors 300 or 500 executes the guarded demo prolog/epilogue and compares canonical body frames.
Windows restores all 362 native instruction-boundary contexts and four called-leaf contexts through the expanded caller.
Two stale allocation/save metadata controls fail. All owned function-table registrations disappear after the comparison.
The existing temporal caller comparison still passes all 748 contexts with the shared fixture.
Both demo owners require exact GS metadata and complete native handler/common/security-cookie leaf guards before preparation.
Test-DemoHandlers.py executes eighteen native handler cases, including untranslated frames, stale offsets, and invalid cookie high bits.
Four valid frames return ExceptionContinueSearch; fourteen bad cases reach the native cookie failure branch. Six changed bindings refuse preparation.
Test-DemoHandlerWindows.ps1 runs stock, 300-actor, and 500-actor native frame setup/teardown and complete GS helpers under actual Windows dispatch.
Three normal returns and three exceptions pass; twelve owned function records disappear after deletion.
Stale handler cookie data and invalid global cookie high bits reach the native failure branch in separate processes.
This Windows fixture uses an authored body and owned cookie/exception/failure bindings. Real game registration remains unverified.
The writer/reader packet tests still use authored cookie/clear endpoints, demo context and mode, actor state exports, little-endian long dispatch, and field flags.
Whole game callers, complete save behavior, runtime registrations, and game/peer lifecycle remain admission requirements.
No installed payload changes in these preparation tests.

continuation_jump emits a neutral REX-prefixed relative jump inside each existing active-frame source window.
Plain external E9 entries can be recognized as completed epilogues even though the native allocation remains active.
The failing source comparison was separate from the earlier successful helper instruction comparisons.
The corrected entry preserves the original target, flags, registers, stack, and guarded extent without an extra call.
The exact five-byte LEA/RET terminal leaf at 0x2505b9b retains its separate plain transfer contract.
Short or unknown active-frame windows refuse preparation; no extra native byte is stolen.
BO3NFUW2 adds the complete actual source replacement to the existing owned Windows fixture.
Each shape passes all 79 server entry comparisons and two snapshot entries; the allocation entry also passes.
The corresponding plain-jump mutations fail. All 1,834 server helper, nine snapshot, and seven allocation boundaries still pass.
Ten real CPU comparisons execute forward/backward plain and prefixed jumps and preserve the selected argument and arithmetic flags.
Exact game registration, handler bridges, saves, remaining consumers, and real peer behavior remain unverified.

provenance.json records the owner's authorized local AAE prototype and original source hashes.
This directory contains Python source and address/hash contracts. It contains no game executable or extracted game bodies.
