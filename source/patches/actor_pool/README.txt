ACTOR STORAGE AND EXTERNAL SENTIENT TABLE IMPLEMENTATION

Status: owned native replay only. No deployable 200-actor patch exists.

table_layout.py defines the exact 240-sentient address contract.
It retains 0x3088-byte native records and separates two 240-by-240 tables.
Their native offsets are 0x12A0 with 0x48-byte entries and 0x112C with two-byte entries.
It rejects invalid owners, unsupported capacities, address wrap, and overlapping table storage.
This capacity preserves the stock difference of forty between actor and sentient counts.
That difference remains a sizing hypothesis.

x64_table.py emits an external accessor and individual guarded member rewrites.
Each member rewrite preserves input flags, unrelated registers, and the original operation's output flags.
Six known sites use explicit owner bindings because their memory base contains an offset or a folded table address.
The emitter retains each original field operation while changing its memory address.
It also emits map, allocation, load, and count stubs.

table_plan.py prepares 141 exact edits for the supported captured stock executable.
It emits seventy-one known entry-table consumers, four indexed-WORD consumers, and the external accessor.
Folded four-byte producers preserve the next instruction after restoring the stub stack.
It clears the full matrix before native map initialization.
It clears an owner row before native allocation publishes the sentient to its entity.
It redirects the native target-entry reset and load clear loop.
It widens the three native sentient-free owner counts without changing their signed branch conditions.
It retargets both real actor constructor and destructor registrations and sets their imm32 counts to 200.
storage_plan.py relocates known static sentient and secondary-actor references and per-sentient handle heads.
It expands the known allocator, iterator, clear and record-count bounds together.
StorageLayout requires aligned, non-overlapping regions for every expanded array.
It leaves the shared 2,047-node handle pool unchanged.

PreparedTablePlan.require_activation() refuses activation.
Unclassified consumers, save framing, AAE consumers, and startup admission remain unresolved.
New stubs also need registered native unwind records before live execution.
Stubs entered from an existing native frame must chain its exact unwind record.
A leaf unwind record cannot describe that continuation frame.
The new load record count cannot read a stock 104-record stream without an admitted framing strategy.
codec_contract.json identifies the exact native count sites and their legacy/combined-format requirements.
Both indexed tables are discarded by the stock reader. Preserve that reset behavior rather than adding them to the payload.
Legacy and VM-only formats must still consume 64 actors, 104 sentients and 64 secondary records.
The combined format consumes 200 actors, 240 sentients and 200 secondary records.
No outer format admission or dynamic per-load count binding is implemented here.

implementation_plan.json records the actionable edit guards and remaining gates.
It contains no replacement bytes or original game bytes.
Prepare-TablePlan.py exports emitted stubs and replacement bytes to a new private lab directory.
Its addresses describe owned replay allocations. They are not admitted live allocations or packed executable offsets.

Repeat preparation:
python source/patches/actor_pool/Prepare-TablePlan.py --module <exact-private-module.json> --output <new-private-lab-directory>

Repeat the owned native replay:
python source/tests/actor-pool/Test-ExternalSentientTable.py --module <exact-private-module.json> --dependencies <unicorn-directory> --output <new-private-lab-result.json>

The replay uses original captured instructions and emitted stubs in Unicorn.
It checks 375 direct-instruction states, twenty-five accessor pairs, lifecycle resets, and real actor construction and cleanup.
It executes the expanded native allocator and iterator boundaries and rejects full pools.
The replay passes ninety-one groups. Those groups establish owned instruction behavior.
The free-owner selection case records native reset arguments. Its downstream routines use owned RET stand-ins in that specific case.
The separate target-reset replay executes the actual reset prefix and its nine rewritten memory operations.
The result records code guards, emitted-code hashes, source hashes, and the exact module-manifest hash.
It does not launch BO3, execute Windows exception unwinding, or validate multiplayer.
