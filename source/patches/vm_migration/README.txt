Migration integration candidate

MigrationPlan prepares checked writes for the paused startup transaction.
It admits 500,001 total server slots, eighteen client roots, and a 32 MiB migration buffer.
The one-million-slot migration policy remains refused. Its scalar stream alone exceeds the reviewed transport limit before compression.
These files do not launch or modify a game.

Build and publication

Compile Admission.cpp, VersionGate.asm and Reentries.asm into the pre-import helper.
Compile MigrationPlan.cpp into the parent launcher. It performs no process writes.
Resolve helper exports from the admitted helper PE before constructing HelperOffsets.
The six handler and original arrays use Hook enum order: Header, Data, HeaderAck, SendHeader, Load, Flush.
The two additional handler offsets are SendHeaderAck and MigrationVersionGate.
The five binding offsets identify Bo3MigrationBindings, Bo3MigrationVersionBranches, Bo3MigrationLoadBindings, Bo3MigrationReentries and Bo3MigrationFlushBindings.

Reserve 192 nearby relay bytes. The core plan uses the first 64 bytes.
Pass the following 128 bytes to BuildMigrationPlan.
Every relay uses FF25, a RIP-relative indirect jump, followed by its eight-byte destination.
The relay preserves EAX at the loader version check.
The qualified acknowledgement site uses CALL E8. All other sites use JMP E9 with required NOP padding.

Verify the executable identity, inventory code hashes and all unallocated pointer/capacity fields before publication.
The buffer edit changes a shared numeric-mode instruction. The enhanced launcher must admit Zombies only.
Combine the returned sixteen edits with the core plan before constructing one PausedPatch transaction.
The five records contain 168 zero-initialized POD bytes. Native reentries and continuation addresses become valid before execution resumes.
The full-load error entry points to the active native Com_Error entry, including the core error prelude and existing AAE chain.
The helper performs no binding-time heap allocation, COM initialization or module lookup.

Admission contract

The wire version identifies format prefix C6, total server capacity and client-root count.
Only the configured enhanced version or stock version three can enter the patched receiver.
The header remains twenty-four bytes. Its magic, positive size and receive budget must also match.
A matching enhanced receiver returns that version DWORD in mhack.
The enhanced sender refuses stock empty or mismatched acknowledgements before native mdata startup.
Native selected-peer and migration-phase checks remain active after admission.

A stock receiver can publish its normal 2.5 MiB buffer and copy the twenty-four-byte enhanced header.
Its empty acknowledgement cannot authorize expanded data blocks.
The patched receiver preserves the empty acknowledgement for stock version-three imports.
The VM state adapter translates the eight-root legacy Zombies stream into the expanded pool.
The full-load wrapper checks the format and budget before MemFile initialization.
Its leaf version gate then admits version three or the configured enhanced version without changing registers or stack.

The native compressed flush reserves a four-byte length prefix.
Its original check permits one, two or three remaining output bytes.
The migration-only guard marks the existing overflow flag and clears buffered bytes before that unsafe prefix write.
Other memory files retain the native flush path.
The stock migration writer checks that overflow flag before sending headers.
This preserves bounded failure. It does not prove every expanded script state fits the buffer.

Validation

Build-Admission.ps1 runs eight admission/unwind groups and three composed-plan groups.
The composed fixture applies real checked writes to an owned Windows snapshot.
It verifies original-byte refusal, rollback, memory protection restoration and reversible removal.
Its before.bin and restored.bin hashes must match.
NativeAdmissionReplay.py runs thirty-seven compiled/captured cases, including actual native compression success and failure.
The native replay uses owned byte-copy, security-cookie, CRC and network callbacks.

Remaining proof

Whole-state string/stack serialization, compressed roundtrip and complete load remain unvalidated.
The native serializer can produce more than the scalar slot stream.
Peer selection and retry behavior must handle a selected stock receiver without an avoidable migration timeout.
Delivery deadlines, the actual game allocator, Steam startup, AAE and matching-peer host/join tests remain required.
This candidate is not a validated game release.
