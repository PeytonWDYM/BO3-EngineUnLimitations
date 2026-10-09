# Fixed comparison preparation

Production preparation currently refuses. Captured paths write their raw computed
checksums into game-image chain cells before the comparisons. Changing comparison
flags alone leaves those values wrong. The refusal precedes process inspection.
This module and its owned proof are historical comparison preparation, not an
enabled engine fix.

`PrepareStopped` reads an immutable, exact-build profile and returns checked
`AddressEdit` records. Its caller must own the child, verify and lock the supported
executable file, and keep its job frozen through the entire combined `PausedPatch`
transaction. Pass the complete engine plan for overlap checks. The helper and gate
remain unchanged. Apply, read back, roll back and restore protection through the
existing transaction before thaw; there is no post-thaw maintenance loop.

The public manifest contains RVAs, evaluator families, SHA-256 guard digests and
declared image-relative MOVABS fields. Captured code bodies remain private.
`Generate-Profile.py --output <new-private-Profile.h>` verifies the pinned manifest
before generating the bounded C++ profile. Runtime section-header truncation does
not expand these two exact on-disk code regions.

All 1,365 signatures are admitted. The current structural plan produces 1,353
endpoint edits and retains 12 multi-input transforms. XOR replaces its three-byte
suffix with `xor ecx,ecx; nop`; NEG/ADD replaces its five-byte suffix with
`xor ecx,ecx` and three NOPs; CMP replaces only `cmp eax,edx` with `cmp eax,eax`.
Both CMP loads and their register values remain. XOR/NEG retain the first load and
the matched ECX=0 outcome, but omit the second load. NEG/ADD's other arithmetic
flags may differ; fixed current guards must include the independently traced
equal paths through their overwrite. That is an explicit semantic requirement.

The owned E2E executes authored snippets and applies the real preparation module
to an inert MEM_IMAGE fixture in an owned frozen job. It checks all readbacks,
retained transforms, address normalization, zero-edit refusals, rollback and
protection restoration. It also compiles the module without the owned-test define
and proves the production attribution refusal with an invalid process/base/digest.
Its receipts and source/artifact hashes are private, reproducible evidence. They
do not validate game startup, post-thaw code persistence, expanded allocation,
AAE loading or peer compatibility.
