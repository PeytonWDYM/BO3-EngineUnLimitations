Live entity sampler

This Windows tool reads a verified process without changing target memory.
It requests PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ access (0x1010).
It does not attach a debugger, inject code, suspend threads, or write target memory.

The tool requires 64-bit Python and the snapshot reader dependencies.
Use the private profile verified against the exact executable.
The tool checks the executable hash, loaded image size, timestamp, module path, and process start time.
Supply --expected-start-ticks when another recorder already captured that process instance.
Without this argument, the tool records the instance that it first opens.
It holds that process handle until it stops. It does not reconnect to a reused PID.

Start a sample with a new output path outside the repository:

& $Python source/live/Read-LiveEntities.py --pid $GamePid --profile $PrivateProfile --output $PrivateCapture --rate 10 --duration 60

The default rate is 10 Hz. The maximum rate is 30 Hz.
Set --duration 0 to sample until the process exits or you press Ctrl+C.
Each attempt compares metadata around two full pool reads.
The default is two attempts per sample. --attempts accepts one to four.
The tool delays between sample periods. It does not catch up with a burst of overdue samples.
At 10 Hz, the current stock pool needs about 52 MB of reads per second before retries.
Use a lower rate if capture overhead affects the game.

Each JSONL row has a UTC time and an event name:

attached records the process, executable, profile, rate, and access mask.
sample records checked pool counts, reuse-list state, temporary-event ages, and numeric types.
rejected records failed validation or observed changes. It does not report zero counts.
process_exit records target exit.
stopped records accepted and rejected totals and observed maxima.

Normal active counts include reserved slots. Allocatable counts exclude reserved slots.
Sentinel and fake counts remain separate.
Temporary-event age uses the signed wraparound calculation from the snapshot reader.
The failureCondition field describes the verified normal allocator condition.
It does not identify the cause of Connection Interrupted.
Numeric types have no verified gameplay labels.

Stable metadata and equal pool reads reject observed changes.
They do not create an atomic game snapshot or detect every intermediate change.
Private profiles, addresses, target-derived output, and binaries must stay outside the repository.

Repeat the native E2E test with the fixture and profiles from the snapshot E2E:

& $Python source/tests/Test-LiveEntitySampler.py --fixture $NativeFixture --profiles $PrivateProfiles --output $NewPrivateTestDirectory

The test saves a report and JSONL captures.
It tests counts, recovery states, invalid state, identity checks, target exit, and unchanged target bytes.
It uses a disposable native process. It does not use the game.

For the full E2E, use the PowerShell wrapper with installed Visual Studio C++ build tools:

& source/tests/Test-LiveEntitySampler.ps1 -Python $Python -Fixture $NativeFixture -Profiles $PrivateProfiles -OutputDirectory $NewPrivateTestDirectory

The wrapper also builds a moving-state native fixture.
It verifies observed metadata changes and bounded retries.
