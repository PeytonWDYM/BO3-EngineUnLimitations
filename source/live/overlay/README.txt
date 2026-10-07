The diagnostics window runs outside BO3 and does not consume game input.
It reads the sampler's latest JSON file once per second.
The tray icon can hide the window or close it.
Closing the window does not stop the sampler or recorder.

Start the VM sampler with --latest and a new private JSON path.
Use an exact-build profile and bind the process creation time.
Then start the window:
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File source/live/overlay/Show-Diagnostics.ps1 -Latest C:/private-session/latest.json

Free slots measure reusable script-variable slots, not free entity slots.
Call depth does not count suspended script threads.
The cleanup queue counts the verified deferred entity cleanup chain.
Rejected reads retain the last accepted counters and increase their sample age.
STALE means the last accepted sample is at least five seconds old.
STOPPED means the sampler stopped or the target process exited.
Repeated equal reads do not provide an atomic game snapshot.
Exclusive fullscreen can hide an external window.

Repeat the native sampler verification:
pwsh -NoProfile -File source/tests/vm/Test-VmSampler.ps1 -Python C:/private/python.exe -OutputDirectory C:/private/new-vm-evidence

Repeat the overlay E2E with that owned fixture:
C:/private/python.exe source/tests/vm/Verify-Overlay.py --fixture C:/private/new-vm-evidence/bin/VmPoolFixture.exe --output C:/private/new-overlay-evidence

The overlay E2E retains rendered PNGs, source states, window styles, and JSON results.
It verifies healthy, exhausted, corrupt, uninitialized, and changing native states.
Those fixture checks do not validate moving-game measurements or a game fix.
