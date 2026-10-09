AAE's checksum handler repairs the local computed DWORD and the chained image DWORD.
The later implementation is described in [500K startup](500k-startup.md). The assessment below records its earlier evidence.
That behavior matches the missing operation in the retired comparison-only prototype.
Its availability does not establish an early activation route for the current 500k patch.

The October 8 offline audit reads the saved stock startup snapshot for PID 62740.
Its recorded process start is 2026-10-08T08:53:48.2203149Z.
The audit verifies executable identity, dump process identity, image size, and timestamp.
It checks the saved AAE installer proof against its previously recorded SHA-256.
It hashes the complete 5,765,079,663-byte snapshot and each consulted store span.

| Observation in this snapshot | Result |
| --- | --- |
| Server pool and hash pointers | Both nonzero |
| Client pool and hash pointers | Both nonzero |
| Exact 12-byte original AAE store spans | All 1,069 match |
| Modules with `Overcharged` in their name | None among 141 modules |

The store reads establish that AAE's captured checksum hooks are absent at those fixed sites.
The module list alone cannot exclude private executable allocations.
This snapshot shows initialized VM storage before these AAE hooks appear.
It does not establish the exact first instruction or installation time of the later mod.

The current native transaction requires unallocated server, client, and migration storage.
`source/launch/late_startup/FixedPlan.cpp` rejects nonzero VM pointers before it prepares any edits.
Waiting for the later AAE installation therefore cannot support this transaction unchanged.
Changing allocation instructions after allocation would not enlarge existing storage.
An expansion of existing storage would require a separate, verified lifetime and reference contract.
No such implementation is admitted by this assessment.

The saved full-AAE installer also requires original bytes at its 1,069 fixed store sites.
Its intact table has 1,000 entries, and its split table has 69 entries.
An earlier correction must retain that installer contract and prove its phase handoff.
The saved prefix inventory contains 998 adjacent destination LEAs and 71 transported predecessors.
These counts identify research leads. They do not prove safe continuations or hook publication.

Public [T7Overcharged initialization source](https://github.com/JariKCoding/T7Overcharged/blob/e5f96c89ed7033c140f5a68a11373ed1088b8c41/src/client/main.cpp)
calls component startup from its exported Lua initialization function.
Its [Lua wrapper](https://github.com/JariKCoding/T7Overcharged/blob/e5f96c89ed7033c140f5a68a11373ed1088b8c41/usage/ui/util/T7Overcharged.lua)
loads the DLL and calls that export when the mod initializes it.
That public revision is a reference, not the captured full-AAE v3.9.5 native binary.
Its entry points do not establish an early callback in the supported target.

Private evidence is in `aae-integrity-phase-root-01` under the existing release-enhancement lab.
`Failures.md` precedes `Inspect.py`.
Run the lab Python with `-B Inspect.py --output <new-result.json>`.
The audit reads saved files only and refuses an existing output path.
Two root runs produced byte-identical JSON. They are not an independent review.

No correction hook, native deployment, game launch, or Steam change occurred.
Live 500,000-slot allocation, full-AAE loading with expansion, whole-state migration, and peer compatibility remain unvalidated.
