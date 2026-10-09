# Early checksum correction

This exact-build module corrects 1,069 computed checksum DWORDs before their original image stores.
It preserves the original comparisons and all 1,069 full-AAE installer store sites.
It supports executable SHA-256 `0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0` only.

Each hook replaces one seven-byte destination LEA with a jump to an owned relay.
The relay reads the live expected DWORD through the original frame pointer slot.
It corrects the local DWORD, restores the original destination LEA result, and resumes the original continuation.
EAX receives the expected value, as it does in the healthy original path.
The relay preserves all other registers, flags, and RSP. It uses no callback or runtime instruction decoder.

Preparation checks 14,683 current image guards and 7,950 declared image address fields.
It checks the executable digest, PE identity, MEM_IMAGE ownership, captured protection, and existing edit overlaps.
Declared image addresses must equal the admitted image base plus their recorded RVAs before normalization.
Expected DWORD values remain dynamic. Exact count words and pointer-source instructions remain guarded.
Preparation checks all guards before it allocates the reachable relay arena.

The plan publishes nine RX arena pages and 1,070 source pieces in one stopped transaction.
The source LEA at RVA `1c6aaffe` crosses a page and requires two pieces.
`kPublicationCount` is 1,079. `PreparedPlan::arena` exposes the arena address and size for receipts.
Call `RelayArena::Commit()` only after the transaction commits.
Committed memory remains in the child until process exit, including after the arena owner is released.
For rollback, retain the arena until `PausedPatch` has restored the source hooks.
If restoration fails, keep the child frozen through arena release and terminate it.
Never thaw the job or release its gate after that refusal.

The independent saved-code proof executes all 1,069 setup paths with three expected values per path.
It covers 66 read-to-LEA transports and 71 LEA-to-store transports.
Registers, flags, RSP, frame bytes, and continuation reads and writes match healthy original paths.
Dead scratch bytes below RSP can retain the earlier computed value. The proof checks their later reads and writes.
All original evaluator spans remain disjoint from the source hooks.
The exact full-AAE intact admission words and split transport scan inputs remain unchanged.

The owned Windows proof executes 6,414 authored relay cases and checks complete production-profile admission.
It checks dynamic expected values, fifteen admission refusals, publication, RX protection, arena lifetime, and rollback.
The fixture contains private captured guard bytes, exports inert data, and has no entrypoint.
It never executes captured game instructions. Public source contains only descriptors, RVAs, and digests.

Run `source/tests/early-integrity/Build.ps1` with a new private output directory and the lab Python executable.
The build produces JSON receipts and source and artifact hashes.
These proofs do not validate live BO3 startup, AAE installation, arbitrary incoming control flow, or multiplayer.
The module remains an experimental exact-build candidate until the separate game and peer checks pass.
