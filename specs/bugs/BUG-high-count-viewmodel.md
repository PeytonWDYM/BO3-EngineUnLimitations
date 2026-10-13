# Hand and weapon corruption near 250 actors

## Reproduce

The owner tested Engine Test.10 and AAE Test.38 on Der Eisendrache in PID 63972.
The supported executable hash is `0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0`.
The owner reports hand and weapon corruption near 250 actors.
Two supplied screenshots show displaced hands and absent RK5 geometry during the 300-actor test.
The screenshots show HUD counts near 274 zombies and then 272 zombies plus 28 specials.
Two bounded, non-atomic native flag scans independently recorded 300 allocated actors, including all actor types.

Private screenshots, logs, and their hash receipt are in `actor500-fourth-failure-20261013/session63972`.
The allocation receipt is in `performance-investigation-20261013/read-only-63972/allocated-actor-flags.json`.

## Isolate

The new native TagCache passed the exact runtime gate before and during the match.
The current appended client-actor allocation has full storage for 500 records on both local clients.
Those facts exclude neither other shared resources nor a separate renderer defect.
The later capture and native replay establish CPU skeletal allocation refusal in the reproduced session.

The later Storm Bow server error was `G_Spawn: no free entities`.
It confirms ordinary entity exhaustion and must be investigated separately.
BO3 remained responsive, and no new native dump appeared.

## Hypotheses to verify

1. A remaining actor-index consumer narrows IDs near the byte boundary.
2. A shared DObj, animation, or bone allocator cannot serve the expanded population.
3. A folded client reference still targets original storage or a reserved viewmodel row.
4. A separate effect or weapon path corrupts display state without an actor-index defect.

Do not treat the approximate 250 threshold as proof of an eight-bit wrap.

## Failure cases before patch logic

- Pin the complete native owner, operands, metadata, and source identity before changes.
- Reproduce the defective state in the stock or current complete native path.
- Check sparse actor slots and boundaries 248, 249, 250, 255, 256, 299, 300, and 499.
- Preserve ordinary DObjs, each reserved viewmodel, both local clients, and adjacent storage.
- Preserve source flags, register saves, stack frames, and Windows unwind metadata.
- Test complete allocation, reuse, release, reset, and failure paths for any enlarged shared resource.
- Refuse changed owner bytes or incomplete allocations before publication.
- Separate native replay results from the next high-count game test.

The repair has passed focused native replay, runtime integration, and private installer upgrades.
Gameplay confirmation remains pending.

## Reproduced session evidence

The owner reproduced the distortion in PID 58440, created at FILETIME 134363555051851655.
The paused capture preserved a stable viewmodel DObj handle 1808 with nine models and 133 bones.
Richtofen hands, RK5 geometry, and seven attachment assets were present.
The global DObj free count stayed at 1,481.
This sample does not show DObj-object exhaustion or missing model assets.

A short active capture admitted 79 frame samples.
Observed matrix counts reached 21,352 against 100,000.
Observed model-instance counts reached 2,460 against 50,000.
Observed scene DObj counts reached 421 against 1,024.
These partial-frame samples do not prove every later peak, but they do not justify growing those resources.

The separate CPU skeletal allocator at `0x13C3BA0` has a `0xFFFF0` byte limit.
Its size getter uses the DObj bone count times 32 bytes, with a second copy under native flag `0x400`.
Native reset at `0x135AF70` advances the generation, resets the counter, and publishes the aligned backing pointer.
Wrapper `0x13C85A0` returns a null skeletal pointer and records the failed generation after allocation refusal.
The first-person path at `0x128AD4E` reaches that wrapper through `0x99D930`.

The guarded sticky capture recorded attempted high-water 1,745,760 bytes against capacity 1,048,560 bytes.
It also recorded failed generation 39,211.
Both immediate reads matched under the exact process and native writer guards.
This proves that the reproduced session reached native skeletal allocation refusal.
The sticky values do not identify the exact frame of the reported hand distortion.

Private receipts are in `performance-investigation-20261013/viewmodel-250`.
## Source repair and proof

The physical DObj pool has 3,072 records. Each object supports at most 384 bones and two 32-byte copies.
The repair reserves a separate 72 MiB bank for each local client.
Both banks share the existing owned arena, expanded from 48 MiB to 192 MiB.
The native context layout, atomic reservation, generation, cache reuse, and finite refusal remain unchanged.
A small selector returns the correct bank at native reset.

The native replay reproduces stock refusal after 246 requests of 133 bones.
The new banks admit 3,071 maximum-size requests for each local client.
Repeated replacement can still exhaust a generation. The native null refusal and later reset recovery pass.
The replay covers both wrappers, all 16 encoded-root selector branches, constructor invalidation, and generation wrap.
The exact viewmodel pose owner also follows its native refusal path with its lock and unlock.
Windows execution verifies both bank selections, register and flag behavior, and all five leaf unwind boundaries.

The combined runtime verifies one complete 192 MiB allocation at three image bases.
Both banks retain writable committed storage under that same allocation owner.
Startup refuses an initialized skeletal root before allocation or publication.
Runtime registration, publication, rollback, commit, and removal pass.
Two private packaged Test.10 to Test.11 upgrades preserve existing and absent launch settings and all four payload hashes.

Full model construction, concurrent reset and allocation, native exception dispatch, and live gameplay remain outside these proofs.
The storage size follows the bounded native object domain. It does not follow only the captured high-water value.
