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

## Compatibility

This is a test release. One manual Windows session reached Zombies and verified 500,000 usable server slots.
The client pool and actor limit retain their stock capacities.
Expanded host migration requires matching patched clients. Matching patches alone do not prove compatibility.

The current profile accepts only the executable from Steam depot `311211`, manifest `7651791086710252932`.
Its SHA-256 is `0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0`.
The package includes no game executable or downgrade files.
Other versions, including future updates, require separately verified native profiles.
The installer and launcher refuse unknown versions before patch writes.
They do not reuse offsets from another game build.

**Linux / Proton:** unsupported in this release.
The startup transaction requires job freezing that [Valve's Wine backend](https://github.com/ValveSoftware/wine/blob/bleeding-edge/dlls/ntdll/unix/sync.c) does not implement.
A Proton release needs another verified startup backend and game tests.

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

The setup executable needs a Windows Python 3.12 or later installed in a Wine prefix.
Pass its `python.exe`. The installer E2E runs with the host `python3`.

```sh
WINEPREFIX=~/private/wineprefix pwsh -NoProfile -File scripts/release/Build-Patcher.ps1 -Output ~/private/bo3-500k-build -NativeBuild <verified-native-folder> -Python ~/private/wineprefix/drive_c/Python313/python.exe
```

Under Wine the setup executable refuses every action, so the Linux packaged tests check that refusal.
They do not open the setup window.
Building on Linux does not add Proton support.

## License

This project's source code uses the [MIT License](LICENSE).
You can use, modify, distribute, and sell it. Keep the copyright and license notice with copies.
Third-party components retain their own licenses.

## Credits

Microsoft supplies [Detours](https://github.com/microsoft/Detours).
[Maurice Heumann's integrity-check research](https://momo5502.com/posts/2022-11-17-reverse-engineering-integrity-checks-in-black-ops-3/) informed the checksum work.
The release includes third-party license notices.
