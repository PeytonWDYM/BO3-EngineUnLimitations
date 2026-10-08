Cooperative startup gate prototype

This separate helper has owned native fixture evidence. Actual BO3 gate behavior remains unverified.
Do not deploy it or use it for a BO3 launch without fresh review and root authorization.
On this Windows build, RtlIsThreadWithinLoaderCallout returns zero in an EXE TLS callback.
The owned evidence showed that this query alone admits a wait there. The final admission
also requires a bounded unwind frame in the actual BaseThreadInitThunk runtime-function range.
Owned main CRT calls contain that frame. Matched DLL and EXE TLS calls do not.

The parent creates one suspended child and duplicates ready, release and parent-process
handles into that child. It copies a Detours GUID payload before resuming the primary thread.
GateContract.h defines the 72-byte payload and 120-byte exported state. Payload identity binds
the PID, creation FILETIME, primary thread, parent PID and 128-bit nonce. Production builds
pin a 30000 millisecond deadline. Owned fixture builds pin a 1000 millisecond deadline.

The helper checks object types and handle rights. It rejects two different handles for
the same event with CompareObjectHandles. The Windows SDK OneCore import library provides
that documented function. The ready event must permit signaling. The release event must
permit synchronization. The parent handle must permit synchronization and limited queries.

The API detour always calls the original GetStartupInfoW before gate admission. It preserves
the output, last-error and native unwind path. Only the exact API return, 44 wrapper bytes,
bounded outer CRT return and primary thread can reach loader-state admission. Calls that
fail these checks forward normally without VM reads, ready signals or waiting.
The loader-callout query rejects early DLL calls before unwind work. A bounded native unwind
then checks at most 64 frames against the registered kernel32 BaseThreadInitThunk range.
Missing export, missing registered range or absent frame refuses admission. No guessed stack
word scan or alternate entry anchor is admitted. This Windows entry anchor is not a published
general application API contract. It does not prove every lock is absent.

After admission, one callback publishes Waiting and its identity before signaling ready.
The callback waits for release or parent exit with the fixed deadline. A premature release,
parent loss, wait error or timeout terminates the owned child. A successful release records
Released, then Returned. The coordinator needs no remote state write to release the callback.

The frozen startup probe Observation.cpp is compiled into this helper. It publishes read-only,
provisional storage observations after gate admission. Other threads can still execute.
The callback does not establish all-thread quiescence and performs no native VM/code/DR edits.
The separate late coordinator owns debug attachment, complete paused edits and detach.

Native build and owned E2E recipe:
  pwsh source/tests/startup-gate/Test.ps1 -OutputDirectory <new-private-directory>
    -DetoursRoot <pinned-official-Detours> -Python <existing-lab-python>
    -CallerCapture <verified-snapshot-inspection.json>

The native recipe retains both early DLL and EXE TLS matched-call refusals and main-entry
admission. Its source/build/binary receipts bind the owned proof. Actual BO3 unwind coverage
and late-debugger tolerance require separate root tests. A fixture pass does not validate them.

Loader query ABI source:
  https://github.com/winsiderss/phnt/blob/master/ntrtl.h
Documented loader-callout fail-fast semantics:
  https://learn.microsoft.com/en-us/windows/win32/devnotes/ldrfastfailinloadercallout
Documented underlying-object comparison:
  https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-compareobjecthandles
