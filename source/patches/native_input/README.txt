This experimental candidate addresses a captured full-AAE native input crash.
The custom-key callback attempted a write through a missing UI Lua global context.
The original native instructions reproduce that write in an isolated emulator.

The candidate checks the global context after the original lock acquisition.
An unavailable context skips Lua execution and uses the existing unlock and string cleanup path.
A ready context retains the original compiler, sharing mode changes, and protected call.
The added helper has chained Windows unwind metadata.
Conditional transfers preserve unwinding at the helper branches.

The builder requires a private, exact-hash unpacked image and inspected profile.
Prepare only outside the repository and working game:
python source/patches/native_input/Prepare-LuaGuard.py --source C:/private/original.dll --profile C:/private/profile.json --output C:/private/new-candidate

The private original unpacked image comes from a verified full-AAE module.
UPX integrity checks validate its compressed and expanded payloads.
Header repair and unpacking take place only on a private copy.
The packed original remains the removal artifact. Do not distribute game or mod binaries.

Repeat instruction replay and Windows image/unwind checks:
pwsh -NoProfile -File source/tests/native-input/Test-LuaGuard.ps1 -Python C:/private/python.exe -Original C:/private/original.dll -Candidate C:/private/candidate/T7Overcharged.ff -Profile C:/private/profile.json -Output C:/private/new-evidence

The Python environment needs pefile and Unicorn 2.1.4.
The Windows verifier needs the Visual Studio C++ build tools and Windows SDK.
It maps the PE without executing imports or DllMain and checks six unwind positions.
The emulator uses owned memory and mocks external calls. It does not test the real lock or Lua lifecycle races.
These checks do not prove a successful BO3 launch, mod initialization, custom-key feature, or co-op match.
Normal deployment requires explicit authorization, a verified original backup, and the game closed.
Use source/patches/grenade_cleanup/Manage-Candidate.ps1 with -Patch NativeLuaGuard for this exact candidate.
Its fixed original and candidate hash pair rejects other images. Apply and Remove use the staged record.
The separate grenade cleanup candidate and final engine-patch deliverable remain unvalidated.
