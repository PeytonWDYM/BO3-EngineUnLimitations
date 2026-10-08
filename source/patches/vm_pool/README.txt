VM STATE ADAPTER SOURCE

This source is an integration candidate. It is not a deployable BO3 patch.

StateAdapter retains the engine's per-slot reader and writer through typed native bindings.
NativeStateBridge supplies the captured whole-state tail and capacity-key insertion hook.
The game must preserve one selected capacity throughout the pool lifetime.

The exported Bo3VmStateBindings record has 48 bytes on x64:
  0: imageBase, UINT64
  8: total, UINT32
 12: clientRoots, UINT32
 16: stockClientRoots, UINT32
 20: modePolicy, UINT32 (Any=0, ZombiesOnly=1)
 24: originalClientReader, pointer to void(UINT32, void*)
 32: originalClientWriter, pointer to void(UINT32, void*)
 40: originalInsert, pointer to void(UINT32, UINT32, UINT64, UINT32)

C exports:
  ReadNativeState(UINT32, void*) -> StateError
  WriteNativeState(UINT32, void*) -> StateError
  InsertNativeStateKey(UINT32, UINT32, UINT64, UINT32) -> void
  ClearNativeImportContext() -> void

ReadNativeState and WriteNativeState are status-returning APIs.
Their game detours must handle failure before native continuation.
source/patches/vm_startup/StateErrors.cpp supplies the owned-tested native error wrappers.
Their actual game activation remains incomplete.
The native error path must clear import context before any non-local error exit.

Verify the native code, executable identity, client allocation, and mode policy before publishing bindings.
Publish all bindings and hooks while the allocation gate holds all target threads.
The binding record uses constant initialization. Publishing it needs no remote function call.
Inspect the final helper's imports, TLS, initialization, and resolved dependencies separately.

The expanded header contains five DWORDs: 0x33564d50, 1, total, clientRoots, freeHead.
Matching peers require format admission before transfer. A stream tag alone does not protect unpatched peers.
Legacy input reads exactly 129,999 stock records and preserves slot IDs.
The native bridge translates two verified capacity-derived category-one keys before hash insertion.
The optional enhanced launch selects ZombiesOnly. Server state access then requires native mode zero.
Other modes are refused before stream, pool, hash-table, or tail access. Client serialization remains unchanged.
This protects this serializer's output. It does not guard all native mode transitions or persistent file creation.
Use the separate stock launch for other modes.
The stock-sized writer refuses a changed client-root count before writing any state.

Test-StateAdapter.ps1 creates an owned executable and retains hashes, exports, object symbols, and traces.
NativeStateReplay.py uses verified private captured code and retains full slot streams and round-trip receipts.
Neither harness launches BO3 or changes its installation.

exact_build_inventory.json records the supported executable's count, hook, code, and client-layout guards.
The backing client array has eighteen records. Its stock Zombies stream contains eight roots.
This inventory remains audit-only. It does not enable startup, migration, or campaign compatibility.
Eleven owned state-adapter groups pass, including malformed free chains and the Zombies-only policy.
Fresh bounded review found no remaining source findings or missing free-chain checks.
