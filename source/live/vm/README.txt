Read-only script-variable sampler

Use 64-bit Python on Windows. The reader opens the process with query and VM_READ permissions only.
It verifies the executable hash, loaded module build, module path, and process start time.
The reader does not inject code, write target memory, attach a debugger, or change game files.

Run Read-LiveVm.py with --pid, --profile, and --output.
Keep the profile and output outside the repository. The output file must be new.
The default rate is 10 samples per second. The default duration is 30 seconds.
Use --duration 0 to capture until interruption or process exit.
Use --expected-start-ticks to require a previously recorded process instance.

The profile uses the existing private VM layout fields. It must have status fixture-only or game-validated.
The current game profile remains disabled. Native fixture results do not validate game capture.
The reader accepts one or two instances and at most 130000 slots per instance.
The native layout reserves slot zero. Capacity includes that slot. Usable capacity excludes it.
Free and allocated counts describe the other slots. Numeric type counts include both free and allocated slots.
The reader checks every free slot against the bounded reuse chain. It also checks the deferred entity chain.
A null pool reports an uninitialized instance. It does not report zero allocation.

The reader compares two complete pool reads and repeated metadata and error-text reads.
Unequal reads reject the sample. These consistency checks do not produce an atomic VM snapshot.
First-error text reads have a 1024-byte maximum. A terminator before an inaccessible page stops the read.
The reader compares original message bytes and decodes text as UTF-8 with replacement characters.
Unreadable text does not invalidate the pool count.
Text can precede capture. Its presence alone does not establish the game failure cause.
Current function depth describes nested execution. Numeric slot types do not identify script functions or grenade owners.

Native E2E

Run source/tests/vm/Test-VmSampler.ps1 with -Python and a new -OutputDirectory outside the repository.
The harness builds an owned native fixture with the Visual C++ x64 tools.
It captures healthy, exhausted, recovered, corrupt, changing, unreadable, and exited states.
The result.json file records ten cases. Each capture retains its profile, command, JSONL output, and errors.
The healthy case retains independent SHA256 memory hashes and native fixture checksums before and after capture.
These checks verify the reader against owned processes. Real game validation remains required.
