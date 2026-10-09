Runtime patch-loader foundation

This native Windows x64 tool verifies a target and changes bounded memory records during a reversible session.
The first write contract supports the included native fixture.
Stock BO3 does not provide this contract.
This tool cannot apply a game patch yet.

The loader verifies the executable path, SHA256, x64 PE header, image size, timestamp, and original bytes.
It finds the loaded main executable at its actual ASLR base.
It rejects overlapping records and records outside committed memory in that image.
It changes runtime memory only.
It restores page protections and flushes the instruction cache after each write.
If a later write fails, it attempts to restore records that this session changed.
Removal checks all replacement bytes before it restores the original bytes.
If another writer changed bytes, removal fails and preserves those bytes.

The profile selects the main executable only.
The profile contains an exact executable path and build identity.
It does not select a process by name or inject a DLL.

Build and run the native E2E from the repository root:

source/loader/Build-PatchLoader.ps1 -OutputDirectory C:/private/loader/bin
source/tests/Test-PatchLoader.ps1 -OutputDirectory C:/private/loader/evidence

The build uses the installed Visual Studio x64 C++ tools and Windows SDK.
The EXEs use the static C++ runtime.
No extra runtime package or downloaded library is required.
The test saves profiles, fixture output, loader output, hashes, and result.json in the specified directory.
The test builds a separate rollback executable with a compile-time failure after its first real memory write.
The release executable does not contain this failure path.
Keep this directory outside the public repository or inside its ignored lab directory.

The profile uses UTF-8 text without a byte-order mark:

BO3_RUNTIME_PATCH_PROFILE 1
id fixture-v1
target C:\private\loader\bin\PatchLoaderFixture.exe
sha256 <64 hexadecimal characters from the exact executable>
image_size <decimal PE SizeOfImage>
timestamp <decimal PE timestamp>
safety fixture-cooperative-v2
patch <RVA in decimal or 0x hex> <original hex bytes> <replacement hex bytes>

Put identity fields before patch records.
Each record changes 1 to 4096 bytes without changing its length.
A profile can contain up to 128 records and 65536 total replacement bytes.
The fixture reports its data and instruction RVAs after launch.
The E2E script generates exact profiles from that metadata.
Do not use the example placeholders as a profile.

PatchLoader.exe inspect --profile C:/private/fixture.profile --pid 1234
PatchLoader.exe session --profile C:/private/fixture.profile --pid 1234 --hold-ms 1000

inspect requests process read access and checks identity and original bytes.
session requests write access, applies records, waits, then removes them.
The duration accepts 1 to 60000 milliseconds.
The session keeps one process handle, so PID reuse cannot redirect an existing session.
The loader returns zero on success and one on failure.
Its output includes the profile ID, process ID, ASLR base, image size, executable hash, and action results.

The fixture has one thread.
It stops all patch-location access before it signals its named ready event.
The loader applies and removes records only while that thread waits for the resume event.
Each request has a generation number in a target-owned shared mapping.
The fixture releases a safe point only when the resume generation matches its request.
An old resume event cannot release a new safe point.
A target-owned mutex permits one loader session at a time.
The loader cannot infer this contract from a paused game screen.
Multiple instruction-byte writes are not atomic while target threads run.
A future engine patch needs a verified safe point before it can use this loader.

Each session removes its patch at the end of its duration.
If the target exits, the runtime patch disappears with its address space.
If the loader is killed or crashes, its runtime changes can remain until the target exits.
If byte or protection restoration fails, the loader leaves the fixture at its safe point.
A removal conflict also leaves the fixture at its safe point, even before removal changes bytes.
Restart the fixture to recover from an interrupted session.
The current tool does not install a game patch, offer a GUI, or handle game sessions.
Fixture success does not establish game stability or compatibility with mods and friends.
