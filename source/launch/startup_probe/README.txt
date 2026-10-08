Observation-only startup API probe

This separate private helper observes the supported stock executable. It does not activate
larger pools, install VM codecs, wait for a parent, change debug registers or bypass protected checks.
The deployed enhanced helper remains unchanged. This probe reuses the reviewed Control08 source,
compiled with a different helper hash. Its Bo3EnhancedHelper.dll filename exists only in the new
private probe directory. Do not copy it over the deployed helper.

Build and native owned E2E:
  pwsh source/tests/startup-probe/Test.ps1 -OutputDirectory <new-private-directory>
    -DetoursRoot <pinned-official-Detours> -Python <existing-lab-python>
    -CallerCapture <verified-snapshot-inspection.json>

The production subdirectory contains the fixed stock controller, new probe helper and Detours
license. The controller uses the existing syntax:
  BO3-Startup-Control.exe --no-debugger --observe-seconds 120 <BlackOps3.exe>
    <new-private.jsonl> [unchanged game arguments]
Only Peyton or the authorized root task may run the actual game after fresh review.

The helper forwards every GetStartupInfoW call to its saved original. It restores that call's
last-error value after observation. Only the exact API return RVA 2be2032 and all 44 caller bytes
permit VM reads. Counters rejected/dropped/vmReads separate guard refusal, publication collision
and actual bounded observation reads. Nonmatching callers read no VM globals.

Exports:
  Bo3EnhancedBoot: unchanged 24-byte Control08 boot ABI.
  Bo3StartupProbeCounters: 48bytes, ABI 1. Atomic counters precede imageBase and originalTrampoline.
  Bo3StartupProbeObservation: 200bytes, ABI 1. sequence at 8, threadId 12, count 16, returnSite 24,
    wrapperCallerReturn 32, wrapperCallerReadable 40, wrapperCallerMatches 44, readableMask 48,
    reserved 52, pools 56(4QWORD), migrationPointers 88(5QWORD), migrationSizes 128(3DWORD),
    caller 140(44bytes), allocatorPrefix 184(16bytes).

Accept a helper publication only after identical copies with the same even sequence. A count of
zero means no accepted caller observation. The readable mask uses bits 0..3 for server pool/hash
and client pool/hash,4..8 for migration pointers,9..11 for migration sizes and12 for allocator bytes.
Ignore a value whose read bit is absent. These sequential native reads are provisional.
They are not an atomic native-world snapshot or proof that other threads are paused.

The verified wrapper subtracts 0x98 from RSP. Its saved caller return lies 0xa0 above the API return
slot. The probe uses the compiler return-slot intrinsic, current-thread stack bounds and a checked
ReadProcessMemory before reporting that word. It compares the word with verified CRT returnRVA
2bd4124. This records a caller candidate. It does not establish outside-loader or publication safety.
The sixteen allocator bytes are an early plaintext observation, not complete VM code admission.

DllMain restores Detours imports, checks bounded PE identity, installs the API detour on the
current thread and publishes POD boot fields. It does not construct a runtime or synchronize.
The owned fixtures prove API behavior, early DLL/TLS readiness, coherent helper publication,
Windows exception unwinding, refusal paths and controller identity. Actual BO3 tolerance and
startup observations remain unverified until a reviewed manual Steam test.
