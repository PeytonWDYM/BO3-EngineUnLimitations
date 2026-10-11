DISABLED 300 ACTOR / 340 SENTIENT PREPARATION

This source prepares owned native replays. It cannot activate a game patch.
FixedPlan and the installer do not use this plan.

shape.py supplies every emitted capacity and storage extent.
The forty extra sentients preserve the stock count difference. Actual demand remains unmeasured.
Native actor records retain stride 0x2110. Native sentient records retain stride 0x3088.
The two external matrices contain 340-by-340 entries of 72 bytes and two bytes.
Storage includes actors, secondary actors, sentients, both matrices, handle heads, and DObj pointers.
The seven regions use 16,165,640 bytes. Stub storage and allocator overhead are additional.
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

python -B source/patches/actor_pool/Prepare-ActorPlan.py --module <pinned-module.json> --executable <exact-private-executable> --output <new-private-lab-directory>

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
Both temporal preparations stay outside the main plan. History construction/reset, caller buffers, save framing,
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
The owning caller's adjacent actor and corpse buffers still need expansion without changing corpse capacity.
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
It does not implement a bridge or verify Windows exception dispatch, native C++ cleanup, or partial-prolog handler suppression.
Test-NativeUnwind.ps1 -IncludeTemporalRestore adds the separate restore stub to the owned comparison.
That run covers 79 continuations and 1,834 boundaries. The restore adds five contexts without temporary stack allocation.
Continuation metadata must preserve the complete native frame and describe added stack phases.
Grouped CHAININFO alone cannot describe an added fixed allocation that differs from the primary frame.
Native handlers, partial prologs, epilogs, and game registration remain activation gates.
Startup must allocate, construct, guard, and roll back all storage before the first native consumer.
Complete consumer coverage, shared handle demand, save behavior, and actual Windows game behavior remain open.

provenance.json records the owner's authorized local AAE prototype and original source hashes.
This directory contains Python source and address/hash contracts. It contains no game executable or extracted game bodies.
