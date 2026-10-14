# Native client cache allocation failure

## Reproduce

The owner reported about 189 zombies and 20 Panzers on Der Eisendrache.
The session used Engine Test.9 and AAE Test.37.
The capacity gate passed, and AAE imported 10% replacements from round 30.

The game wrote `minidumps/crash-2026-10-13-01-34-57.zip` at 06:34:58 UTC on October 13, 2026.
The private evidence folder is `actor500-third-crash-20261013/session42340`.
The dump records PID 42340, creation time 06:29:15 UTC, and the supported executable.
The executable SHA-256 is `0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0`.

The trigger immediately before the crash remains unknown.
The reported counts are owner observations, not an atomic memory inventory.

## Isolate

Auxiliary thread 18484 failed at RVA `0x2BC53CF` in native `memset`.
The exception is a write access violation at address zero.
The captured destination is zero, and the requested size is `0x180` bytes.

The saved return address identifies the call at RVA `0x1CCA59`.
Its complete owner, RVA `0x1CCA10`, allocates a six-row transform cache through native allocator RVA `0x22773A0`.
It requests 384 bytes with 64-byte alignment and stores the result at owner offset `0x630`.
It then clears the result without testing the allocation return.

The allocator dispatches type 2 to native fixed free-list allocation at RVA `0x2275AD0`.
That allocator returns zero when its free list has no suitable block.
The pinned baseline cache heap at RVA `0x421F660` has a 96 KiB capacity.
The current dump does not yet prove the heap's free-list contents at the fault.

## Hypothesize

1. The stock cache heap cannot serve the larger actor population. Replay its complete creation and allocation paths to the first refusal.
2. Cache blocks leak during reuse or teardown. Replay releases, coalescing, reset, and later allocation before a capacity change.
3. The allocator object or free list is corrupt. Check exact owner guards and list invariants in a coherent capture or replay.
4. System memory is exhausted. The native fixed allocator's refusal path must show whether it requests more system memory.

## Verify

The actual dump confirms the null destination and complete immediate caller.
The pinned exact code confirms the allocation arguments and fixed-heap dispatch.
The complete stock native replay exhausts after 219 allocations, with 98,176 bytes used.
The cache owner then reproduces the same zero-address write at RVA `0x2BC53CF`.
Native release, reset, and reuse pass afterward.
The artifact is `session42340/caller-owner-review/native-stock-replay.json`.

The stock centity allocation is `0x3F0000` bytes per local client at stride `0x900`.
It has 1,024 ordinary records and 768 client-only records.
Two supported local clients can therefore own 3,584 cache blocks.
The two extra DObj IDs have no centity cache.
This establishes a capacity defect in the expanded population profile.
The dump does not retain the crash-time free list, so its exact live allocation count remains unknown.

A relocated 2 MiB bank has space for the bounded owner domain, including native alignment and headers.
The proposed arena interval is `+0x2D00000` through `+0x2F00000`.
It intersects no current storage interval.
The synthetic client address model produces identical edits when moved elsewhere.

The native constructor skips initialization when its published root is nonzero.
Startup must refuse that state before publishing the constructor changes.
The generated constructor edits passed complete native creation, lookup, allocation, release, fragmentation, coalescing, reset, and reuse.
One client uses 802,880 bytes for 1,792 owners. Two clients use 1,605,696 bytes for 3,584 owners.
The 2 MiB bank has 491,456 bytes left at that maximum.
Each owner has one 384-byte payload containing six 64-byte cache rows.
Native alignment and headers consume 448 bytes per allocation, plus the 64-byte heap header.
Duplicate and full-table lookups preserve allocation usage. Fragmented reuse preserves live payloads and edge canaries.
The source E2E refuses 23 changed native code, metadata, and dispatch guards, plus five invalid storage spans.
The bounded candidate still refuses allocation beyond its finite capacity of 4,680 complete payloads.
It retains the original cache owner's null-clear failure path beyond that unsupported domain.
The artifact is `session42340/caller-owner-review/source-e2e-01/result.json`.

Test.10 declares the complete bank in the actor recipe and adds the cache root to cold admission.
Windows transaction checks refuse a nonzero root before any source publication at three game bases.
Rollback, commit, registration, removal, exact source refusal, and allocation cleanup pass.
The patch changes only the native constructor capacity and backing operands. It preserves native frames and cache algorithms.
These fixtures replace profiler and TLS tracking endpoints. They execute native heap and cache algorithms with owned inputs.
Concurrent contention, full centity/map teardown, a matching-peer session, and live high-count gameplay still need separate tests.

## Failure cases before patch logic

- Refuse a different executable, code owner, constructor, dispatch table, or cache layout.
- Reproduce the stock null return with complete native allocation and cache initialization.
- Preserve allocation alignment, headers, canaries, owner pointers, and six cache rows.
- Preserve reuse of an existing cache and the native key lookup.
- Preserve native release, coalescing, reset, and allocation after reset.
- Check all supported local clients and the last admitted cache owner.
- Refuse a changed capacity edit before any patch publication.
- Preserve Windows unwind metadata and all original registers and flags.
- Keep the game and peer test separate from native replay results.
