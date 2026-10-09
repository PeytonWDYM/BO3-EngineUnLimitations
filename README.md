(Note: fully vibed. Was annoyed about how easily the server instance can crash whilst playing. took me a day to do with GPT 6.1 Sol. Feel free to modify in any way)

# BO3 500K

An optional 500,000-slot server script-variable pool for Steam Black Ops III Zombies.
The launcher applies the patch in memory before the game allocates its script pool.
The installer adds a reversible Steam launch option. Original game files stay unchanged.

## Install

1. Download the Windows package from [Releases](https://github.com/PeytonWDYM/BO3-EngineUnLimitations/releases).
2. Extract the ZIP.
3. Close Steam and Black Ops III.
4. Start `BO3-500K-Setup.exe`.
5. Select the game folder and click **Install**.
6. Open Steam and select **Play**, then select Zombies.

Keep the launcher window open while playing. Closing it ends its game process.
To remove the patch, close Steam and the game, start the installer, and click **Remove**.
Removal restores your previous Steam launch options.

Source-built launchers also accept `--skip-intro` after the game executable path.
It skips the startup logo through a guarded engine instruction edit in the same
stopped transaction as 500K. Game video files and other cinematic calls remain intact.
Without the flag, the startup logo retains its original behavior.

## Compatibility

This is a test release. One manual Windows session reached Zombies and verified 500,000 usable server slots.
The client pool and actor limit retain their stock capacities.
Expanded host migration requires matching patched clients. Matching patches alone do not prove compatibility.

The current profile accepts the build from Steam depot `311211`, manifest `7651791086710252932`.
That build has PE timestamp `1765634846` and image size `494186496`.
Any copy of that build is accepted, whatever its SHA-256. Copies can differ outside the code, such as in the signature.
Before any write, the launcher checks the game's code in memory and refuses a copy whose code differs.
The package includes no game executable or downgrade files.
Other versions, including future updates, require separately verified native profiles.
The installer and launcher refuse unknown versions before patch writes.
They do not reuse offsets from another game build.

**Linux / Proton:** the source contains an experimental startup backend. Released packages remain unvalidated for Proton.
When Wine returns `STATUS_NOT_IMPLEMENTED` for job freezing, the launcher suspends its owned process and verifies that every existing thread has stopped and the thread inventory stays unchanged.
The job still owns exactly one game process and kills it on refusal or launcher exit.
Windows retains job freezing. Wine also gets a checked loader-lock query and admission for executable copy-on-write image pages; all existing native code guards remain required.

A private test on Proton Experimental `experimental-11.0-20261001-x86_64` committed all 1,121 startup edits and reached both a vanilla Shadows of Evil solo match and a full All-around Enhancement match.
A read-only check verified all 19 server-count instructions, the complete 32,000,064-byte server pool, its 2,000,004-byte hash allocation, and the free-slot chain through slot 500,000.
This verifies startup and live allocation in that session, not full compatibility.
The player confirmed that the full AAE map and pause menu loaded successfully after correcting the private folder layout.
An earlier flat-folder test reported UI Error 46507 in vanilla; vanilla pause has not been retested in the corrected layout.
Save data, matching peers, host migration, and other Proton versions remain unverified.
Use a private game copy and prefix for further tests. The Windows setup executable still refuses Wine.

### Private Proton launch

Build the native candidate from source, then copy its three native files into `launcher` below.
Use the profiled executable and private copies of player and Workshop files. Keep the normal Steam directory relationships:

```text
private-root/
  Launch-Private.sh
  launcher/
    BO3-500K-Zombies.exe
    Bo3EnhancedHelper.dll
    Bo3StartupGate.dll
  steamapps/
    common/BlackOps3/        # private game, including players
    workshop/content/311210/ # copied subscribed mod folders, preserving their IDs
```

Copy `scripts/proton/Launch-Private.sh` into this root and make it executable.
Set the game's Steam launch option to:

```text
"/absolute/private-root/Launch-Private.sh" "/absolute/private-root" %command%
```

Both paths must be accessible to Steam, including its Flatpak sandbox when applicable.
The wrapper sets the private working directory and creates a separate Proton prefix in `compatdata`.
It defaults to patched mode. Put `stock` or `patch` in `private-root/mode` to select an unpatched or patched private run.
Keep the launcher console open while playing. Restore your previous Steam launch option to remove this wrapper.

To enable the optional engine intro skip in patched mode, prefix that launch option with
`BO3_500K_SKIP_INTRO=1`. Its receipt records `startupIntroSkipped: true` and requires
all 1,122 edits. The live checker verifies the intro instruction along with the 500K pool.
An isolated Proton startup test with the original logo video present reached the menu
and verified the complete live pool with this option. Do not run two BO3 copies on
the same Steam account at once; that interrupts the game's sign-in session.

A source-built launcher also accepts `--custom-intro`. It redirects the startup movie
through guarded engine edits and plays its separate stereo PCM audio inside the game.
The original video files remain intact. Custom mode requires all 1,128 startup edits.
The launcher refuses a missing video or audio file before creating the game.

Prepare a local clip and a private decoder outside Git:

```sh
python3 scripts/proton/Prepare-Intro.py /absolute/local-clip.mkv /absolute/prepared-intro
bash scripts/proton/Build-IntroCodec.sh /absolute/intro-codec-build
```

Copy the two prepared files into the private game's `video` directory. BO3's older
Matroska reader needs positive size integers and a single AVC SPS/PPS pair; the
preparation script writes that layout and a 48-kHz stereo PCM WAV. It needs `ffmpeg`.
The decoder build needs a C compiler, make, curl and tar. It retains the pinned
FFmpeg source and LGPL license outside Git. Clips and binaries are not bundled here.

For Proton, wrap the existing Steam runtime command with
`scripts/proton/Use-IntroCodec.sh <codec-build/codec> <existing-command...>`.
It verifies the decoder checksums and inserts the matching libraries immediately
before Proton inside Steam's runtime. Use a decoder path without spaces or colons.
Steam's decoder refused H.264 in the isolated test; the private matching decoder
produced frames. This does not establish compatibility with other Proton builds.

A private run on the Proton build above displayed the supplied clip, captured its
full audio during playback, and reached the menu with all 1,128 edits committed.
The read-only check verified all 19 count instructions, both complete allocations,
and the free-slot chain through slot 500,000. Audio follows the native movie entry
and decoded-player update, rather than the later startup polling loop. Save, peer,
migration, and other cinematic formats were not retested for this option.

`scripts/proton/Launch-Installed.sh` can be copied into an authorized installation's
`BO3-500K` folder as `Launch-Steam.sh`, beside the native files and `Use-IntroCodec.sh`.
Put `custom` in `intro-mode` and the decoder folder's absolute path in `intro-codec.path`.
The wrapper forwards Steam's command and selects exactly one intro mode; `stock`
and `skip` are also accepted. Test new candidates on private copies first.

AAE's Lua loader resolves `../../workshop/content/311210/<mod-ID>/T7Overcharged.ff` from the game directory and requests `quit` if its helper cannot load.
A flat private game directory breaks that relationship. Preserve the layout above for both stock and patched comparisons.
Do not replace missing mod dependencies by removing version checks or native code guards.

## Build and contribute

Use Python 3.12 or later, PowerShell 7, and Windows x64.
Install Visual Studio C++ tools and the Windows SDK to rebuild the native launcher.

```powershell
python -B source/tests/Test-Installer.py --output C:/private/bo3-500k-tests
pwsh -NoProfile -File scripts/release/Build-Patcher.ps1 -Output C:/private/bo3-500k-build -NativeBuild <verified-native-folder> -Python python
```

Use new output folders outside the repository.
The setup executable contains the native launcher, both helpers, and their verified file hashes.
Users do not need Python or C++ tools.
Use `scripts/release/Build-Native.ps1` to rebuild the native files from source with official Detours v4.0.1.
New native builds need admission, rollback, startup, and peer checks before release.

```powershell
python -m pip install --require-hashes --only-binary=:all: -r scripts/release/requirements-native.txt
pwsh -NoProfile -File scripts/release/Build-Native.ps1 -Output C:/private/bo3-native -DetoursRoot <Detours-v4.0.1-folder> -Python python
```

The native source build produces an unvalidated candidate. It does not update the release's approved file hashes.
Download the native developer ZIP from the test release to rebuild the installer with the approved payload.

### Build on Linux

The same scripts run on Linux x64 with PowerShell 7, Wine, and MSVC from [msvc-wine](https://github.com/mstorsjo/msvc-wine).
Downloading MSVC means you accept the Visual Studio license.
On Arch-based systems, install `wine`, `msitools`, and `powershell-bin`.

```sh
git clone https://github.com/mstorsjo/msvc-wine ~/src/msvc-wine
~/src/msvc-wine/vsdownload.py --accept-license --architecture x64 --host-arch x64 --dest ~/msvc
~/src/msvc-wine/install.sh ~/msvc
git clone https://github.com/microsoft/Detours.git ~/src/Detours
git -C ~/src/Detours checkout e4bfd6b03e50de46b47abfbd1e46b384f0c5f833
(cd ~/src/Detours/src && PATH=~/msvc/bin/x64:$PATH nmake /nologo)
python3 -m venv ~/venvs/bo3-500k
~/venvs/bo3-500k/bin/pip install --require-hashes --only-binary=:all: -r scripts/release/requirements-native.txt
pwsh -NoProfile -File scripts/release/Build-Native.ps1 -Output ~/private/bo3-native -DetoursRoot ~/src/Detours -Python ~/venvs/bo3-500k/bin/python
pwsh -NoProfile -File source/tests/vm-pool/Test-StateAdapter.ps1 -OutputDirectory ~/private/state-tests -Python ~/venvs/bo3-500k/bin/python
pwsh -NoProfile -File source/tests/vm-migration/Build-Admission.ps1 -OutputDirectory ~/private/migration-tests -Python ~/venvs/bo3-500k/bin/python
```

The scripts look for msvc-wine in `~/msvc`. Set `MSVC_ROOT` to use another folder, and `WINE` to use another Wine binary.
Test programs run through Wine.

`source/tests/game-identity/Test-LauncherIdentity.py` runs a built launcher through Wine against private copies of your game executable.
It uses `--verify-build` to check PE identity without starting the game or writing patches.
Copies of the profiled build are admitted and other builds are refused. Runtime code admission is checked separately. Use a private `WINEPREFIX`.

The Proton startup fixtures exercise stopped worker threads, changed thread inventories, loader-lock ownership, image protections, publication, and rollback:

```sh
WINEPREFIX=~/private/wineprefix pwsh -NoProfile -File source/tests/process-freeze/Test-ProcessSuspend.ps1 -OutputDirectory ~/private/suspend-tests
WINEPREFIX=~/private/wineprefix pwsh -NoProfile -File source/tests/startup-loader/Test-LoaderSafety.ps1 -OutputDirectory ~/private/loader-tests
WINEPREFIX=~/private/wineprefix pwsh -NoProfile -File source/tests/image-memory/Test-ImageMemory.ps1 -OutputDirectory ~/private/image-tests
WINEPREFIX=~/private/wineprefix pwsh -NoProfile -File source/tests/startup-intro/Test-Intro.ps1 -OutputDirectory ~/private/intro-tests
python3 -B source/tests/proton/Test-SteamWrapper.py --output ~/private/wrapper-tests
python3 -B source/tests/game-identity/Check-ProtonPool.py --pid <host-game-pid> --game <private-BlackOps3.exe> --receipt <committed-session.json> --output ~/private/live-pool.json
```

The live check only reads the selected process and refuses mismatched executable and receipt identities. Run it after a map loads; a changing free-slot chain can require another snapshot.
Keep receipts and test results outside Git. Fixture results do not replace save or peer tests.

The setup executable needs a Windows Python 3.12 or later installed in a Wine prefix.
Pass its `python.exe`. The installer E2E runs with the host `python3`.

```sh
WINEPREFIX=~/private/wineprefix pwsh -NoProfile -File scripts/release/Build-Patcher.ps1 -Output ~/private/bo3-500k-build -NativeBuild <verified-native-folder> -Python ~/private/wineprefix/drive_c/Python313/python.exe
```

Under Wine the setup executable refuses every action, so the Linux packaged tests check that refusal.
They do not open the setup window.
Building on Linux does not validate a Proton release.

## License

This project's source code uses the [MIT License](LICENSE).
You can use, modify, distribute, and sell it. Keep the copyright and license notice with copies.
Third-party components retain their own licenses.

## Credits

Microsoft supplies [Detours](https://github.com/microsoft/Detours).
[Maurice Heumann's integrity-check research](https://momo5502.com/posts/2022-11-17-reverse-engineering-integrity-checks-in-black-ops-3/) informed the checksum work.
The release includes third-party license notices.
