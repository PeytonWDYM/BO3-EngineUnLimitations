# Animation-info exhaustion near 300 actors

## Reproduce

The owner tested Engine Test.11 and AAE Test.39 after both installed candidates passed hash and route checks.
The owner reports about 280 zombies and 20 Panzers before the server instance ended.
The supplied screenshot reads `exceeded maximum number of anim info`.
The owner also reports a giant zombie pile with no apparent collision.
The piled zombies were still moving and animating.
The owner confirmed that hands rendered correctly in this Test.11 session.

BO3 was closed when this investigation started. Steam remained open.
The two current game logs and the supplied screenshot have stable private copies and SHA-256 receipts.
They are in `actor500-test11-anim-info-failure-20261014` outside Git.

## Isolate

The exact error belongs to native allocator `0x22C6440` through `0x22C66CD`.
It allocates 88-byte animation-info records from a global free list.
The error occurs when the 32-bit free-list head is zero.
Native initialization at `0x22C9BD0` builds 6,000 physical rows, including the reserved zero row.
There are 5,999 usable nodes. This resource is separate from the skeletal byte banks repaired in Test.11.

## Hypothesize

1. The larger actor population exhausts the stock animation-info pool. Replay complete native allocation to the same error.
2. Node release leaks records. Replay recursive release, reset, and complete reuse with both adjacent canaries.
3. A remaining index width or folded reference corrupts the free list. Bind all getters, links, consumers, and serialization paths.
4. The zombie pile has a separate avoidance or collision cause. Trace movement and avoidance instead of treating the visual report as proof.

## Verify

Unchanged native replay admits 5,999 allocations and refuses the next request with the exact supplied error.
Native recursive release returns every node. Reset and complete reuse pass.
Both backing canaries and ABI checks pass. The fixture falsifies a basic release leak in those native paths.
It does not prove every live tree lifetime or attribute the collision symptom.
The private receipt is `anim-info-investigation-20261014/lifecycle-stock-result.json`.

The initializer truncates its calculated links to 16 bits before storing them in 32-bit fields.
A repair must derive the safe index domain and complete backing rather than changing only a compare.
The reference audit covers all three executable sections, complete native metadata, and initializer entry points.
The safe constructor-link domain contains 65,536 physical records, including zero as the sentinel.
The source repair provides 65,535 usable nodes in a separate 5.5 MiB bank under the existing arena owner.
It redirects 72 exact pool operands and replaces the complete 150-byte initializer in place.
Five adjacent globals retain their native storage. No new helper frame or save codec is required.

The emitted source matches the private native candidate exactly.
Complete allocation, finite refusal, release, reset, high-index getters, and adjacent canaries pass.
Native archives, clone, and compact snapshots pass with server and both client contexts.
The archives store animation asset IDs. Native loading rebuilds physical node indexes, including indexes above 32,767.
All 191 native code and metadata mutations refuse, as do five invalid identity or bank cases.
The source receipt is `anim-info-investigation-20261014/source-e2e-01/result.json`.

The combined runtime passes publication, rollback, complete allocation ownership, and cold-state refusal at three Windows image bases.
It executes the rendered initializer and verifies all 65,536 links and both reserved-node and adjacent canaries.
The source inventory and generated header match the independently reviewed final profile.
Two actual packaged Test.11-to-Test.12 upgrades pass with both present and absent Steam launch settings.
They preserve all protected files, unrelated account bytes, and all four native payload hashes.
Removal restores the original Steam configuration exactly. Status remains read-only.
Receipts are in `private-test11-to-test12-20261014/fixture-01` and `fixture-02` outside Git.
A new high-count game test remains pending.
The native 16-bit ceiling is finite. These proofs do not guarantee every map's worst-case animation-tree demand.

## Failure cases before patch logic

- Pin the exact executable, allocator, initializer, recursive release, getters, and complete native metadata.
- Reproduce the current error and preserve zero as the free-list sentinel.
- Derive the complete record and index domain, including all truncations and saved references.
- Preserve every native lock, release, tree lifetime, and server/client context contract.
- Refuse changed owners and initialized undersized storage before publication.
- Exercise the full backing, highest valid index, boundary refusal, recursive release, reset, and reuse.
- Verify ASLR, ABI, unwind, publication, rollback, and installed-version upgrade.
- Keep capacity, collision, and performance findings distinct.
- Require game testing before claiming the animation or crowd problem is fixed.
