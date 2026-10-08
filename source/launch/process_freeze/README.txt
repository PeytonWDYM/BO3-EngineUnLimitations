This folder contains an owned-process proof of Windows 11 process-state objects.
It is not part of the BO3 launcher. No production admission or patch transaction
uses this API yet. The fixture reports bypass-thread and controller-death limits.

Primary declaration source:
https://github.com/winsiderss/phnt/blob/53fbbdc5b5d2b08761db1c7b26bfa8c820924356/ntpsapi.h
NtCreateProcessStateChange and NtChangeProcessState require Windows 11.
The native declarations are not a Microsoft compatibility guarantee.

Run source/tests/process-freeze/Build.ps1 with a new private OutputDirectory.
The runner starts only ProcessFreezeProof.exe owned targets and controllers.
Add -JobProof to run the separate pure-job cases.

On OS 26200.9457, existing and future threads with create flag 0x40 execute
while NtChangeProcessState reports successful suspension. Ordinary future
Worker routines remain unentered until resume. A primary-only thread
inventory does not prevent a new bypass thread from entering later.

Closing the final state reference on controller death resumes ordinary workers.
They observe the fixture's partial marker. The separate child-held reference
and controller-only kill-on-close job candidate prevents that observation in
owned ordinary-worker tests. It does not solve bypass-thread execution.

These results block process-state objects as an all-thread publication gate.
Raw native resume may return success after target exit. Use the retained process
handle and exit code to distinguish a dead target from a resumed live target.

The pure-job candidate uses native job class 18 and an exact 16-byte payload.
Flags is 1. Freeze is TRUE or FALSE. All other bytes are zero.
The job must contain exactly the PID and creation time of the owned target.
The parent assigns its noninheritable kill-on-close job before initial resume.
The pure-job controller has no process-state object or child state reference.
Owned job-freeze cases hold existing and future bypass workers on this kernel.
The entry flag observes the Worker routine after its argument and TID accesses.
It does not observe RtlUserThreadStart, loader execution, or a native RIP.
They do not prove BO3 admission, Steam job compatibility, or an arbitrary native
instruction being safe to patch. These are separate integration requirements.
