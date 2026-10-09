#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Output, [Parameter(Mandatory)][string]$DetoursRoot, [string]$Python='python')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../source/launch/enhanced/PhysicalPath.ps1')
. (Join-Path $PSScriptRoot 'Platform.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../..')
$build=PhysicalPath $Output
if ((Test-Path -LiteralPath $build) -or (Test-WithinPath $build $repo)) { throw 'Use a new native build folder outside the repository.' }
$DetoursRoot=PhysicalPath $DetoursRoot
if ((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or (& git -C $DetoursRoot status --porcelain --untracked-files=no)) { throw 'Use unchanged official Detours v4.0.1.' }
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if (!(Test-Path -LiteralPath $library)) { throw 'Build Detours with nmake from an x64 MSVC environment.' }
$msvc=Get-MsvcToolchain
New-Item -ItemType Directory -Path $build | Out-Null
$savedInclude=$env:INCLUDE; $savedLib=$env:LIB
try {
    if ($msvc.Include) { $env:INCLUDE=$msvc.Include; $env:LIB=$msvc.Lib }
    $compiler=$msvc.Cl
    $assembler=$msvc.Ml64
    $flags=@('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2',"/I$build","/I$repo/source/launch/enhanced","/I$DetoursRoot/include")
    $objects=@()
    foreach ($relative in @('startup_intro/OriginalEntries','vm_startup/ErrorPrelude','vm_startup/OriginalEntries','vm_migration/VersionGate','vm_migration/Reentries')) {
        $object=Join-Path $build ($relative.Replace('/','-')+'.obj')
        & $assembler /nologo /c "/Fo$object" (Join-Path $repo "source/patches/$relative.asm")
        if ($LASTEXITCODE -ne 0) { throw 'Native helper assembly failed.' }
        $objects+=$object
    }
    $helper=@('source/launch/enhanced/Helper.cpp','source/patches/vm_pool/StateAdapter.cpp','source/patches/vm_pool/NativeStateBridge.cpp','source/patches/vm_startup/StateErrors.cpp','source/patches/vm_migration/Admission.cpp','source/patches/startup_intro/Audio.cpp','source/patches/startup_intro/Wave.cpp') | ForEach-Object {Join-Path $repo $_}
    & $compiler @flags /LD @helper @objects $library Winmm.lib "/Fo$build/" "/Fe$build/Bo3EnhancedHelper.dll" /link "/DEF:$repo/source/launch/enhanced/Helper.def" /INCREMENTAL:NO /Brepro
    if ($LASTEXITCODE -ne 0) { throw 'Native helper compilation failed.' }
    Copy-Item -LiteralPath (Join-Path $repo 'source/profiles/ProbeProfile.h'),(Join-Path $repo 'source/profiles/GateProfile.h') -Destination $build
    $gate=@('Helper','Admission','Gate','NativeEntry','LoaderSafety') | ForEach-Object {Join-Path $repo "source/launch/startup_gate/$_.cpp"}
    $gate+=Join-Path $repo 'source/launch/startup_probe/Observation.cpp'
    & $compiler @flags /LD @gate $library OneCore.lib "/Fo$build/" "/Fe$build/Bo3StartupGate.dll" /link "/DEF:$repo/source/launch/startup_gate/Helper.def" /INCREMENTAL:NO /Brepro
    if ($LASTEXITCODE -ne 0) { throw 'Startup gate compilation failed.' }
    & $Python -B (Join-Path $repo 'source/launch/enhanced/Merge-Inventory.py') --vm (Join-Path $repo 'source/patches/vm_pool/exact_build_inventory.json') --migration (Join-Path $repo 'source/patches/vm_migration/exact_build_inventory.json') --output (Join-Path $build 'merged-inventory.json')
    if ($LASTEXITCODE -ne 0) { throw 'Native inventory merge failed.' }
    & $Python -B (Join-Path $repo 'source/launch/enhanced/Generate-GameProfile.py') --inventory (Join-Path $build 'merged-inventory.json') --output (Join-Path $build 'GameManifest.h')
    if ($LASTEXITCODE -ne 0) { throw 'Game profile generation failed.' }
    & $Python -B (Join-Path $repo 'source/launch/job_startup/Generate-WaitProfile.py') --gate (Join-Path $build 'Bo3StartupGate.dll') --output (Join-Path $build 'GateWaitProfile.h')
    if ($LASTEXITCODE -ne 0) { throw 'Gate wait profile generation failed.' }
    & $Python -B (Join-Path $repo 'source/launch/job_startup/Generate-RuntimeProfile.py') --output (Join-Path $build 'RuntimeUnwindProfile.h')
    if ($LASTEXITCODE -ne 0) { throw 'Runtime unwind profile generation failed.' }
    & $Python -B (Join-Path $repo 'source/patches/early_integrity/Generate-Profile.py') --output (Join-Path $build 'EarlyIntegrityProfile.h')
    if ($LASTEXITCODE -ne 0) { throw 'Checksum profile generation failed.' }
    $manifest=Get-Content -LiteralPath (Join-Path $repo 'source/release.json') -Raw | ConvertFrom-Json
    $gameTimestamp=[uint32]$manifest.builds[0].gameTimestamp
    $gameImageSize=[uint32]$manifest.builds[0].gameImageSize
    $helperHash=(Get-FileHash -LiteralPath (Join-Path $build 'Bo3EnhancedHelper.dll')).Hash.ToLowerInvariant()
    $gateHash=(Get-FileHash -LiteralPath (Join-Path $build 'Bo3StartupGate.dll')).Hash.ToLowerInvariant()
    @('#pragma once','#include <cstdint>','constexpr wchar_t kRepositoryRoot[]=L".";',"constexpr std::uint32_t kGameTimestamp=$gameTimestamp;","constexpr std::uint32_t kGameImageSize=$gameImageSize;","constexpr char kHelperHash[]=`"$helperHash`";","constexpr char kGateHash[]=`"$gateHash`";") | Set-Content -LiteralPath (Join-Path $build 'BuildIdentity.h') -Encoding ascii
    $launcher=@('OwnedChild','MappedGate','FixedPlan','PrivateReceipt') | ForEach-Object {Join-Path $repo "source/launch/late_startup/$_.cpp"}
    $launcher+=@('Coordinator','OwnedJob','PrimaryAdmission','RuntimeUnwind') | ForEach-Object {Join-Path $repo "source/launch/job_startup/$_.cpp"}
    $launcher+=@('NativeJobFreeze','NativeState') | ForEach-Object {Join-Path $repo "source/launch/process_freeze/$_.cpp"}
    $launcher+=@('MappedHelper','GameProfile','SteamContext') | ForEach-Object {Join-Path $repo "source/launch/enhanced/$_.cpp"}
    $launcher+=Join-Path $repo 'source/launch/preentry/Identity.cpp'
    $launcher+=@('vm_startup/PausedPatch','vm_startup/NativePlan','vm_startup/NearRelay','vm_migration/MigrationPlan') | ForEach-Object {Join-Path $repo "source/patches/$_.cpp"}
    $launcher+=@('Integration','Launcher') | ForEach-Object {Join-Path $repo "source/launch/early_startup/$_.cpp"}
    $launcher+=Join-Path $repo 'source/patches/early_integrity/Plan.cpp'
    $launcher+=Join-Path $repo 'source/patches/early_integrity/ImageMemory.cpp'
    & $compiler @flags /DBO3_JOB_STARTUP /DBO3_EARLY_STARTUP "/I$repo/source/patches/early_integrity" @launcher $library "/Fo$build/" "/Fe$build/BO3-500K-Zombies.exe" /link bcrypt.lib shell32.lib ole32.lib dbghelp.lib /OPT:REF /INCREMENTAL:NO /Brepro
    if ($LASTEXITCODE -ne 0) { throw '500K launcher compilation failed.' }
    Copy-Item -LiteralPath (Join-Path $DetoursRoot 'LICENSE.md') -Destination (Join-Path $build 'Detours-LICENSE.md')
    & $Python -B (Join-Path $repo 'source/launch/early_startup/Audit-Artifact.py') --directory $build
    if ($LASTEXITCODE -ne 0) { throw 'Native artifact audit failed.' }
    @{status='unvalidated-source-build';gameTimestamp=$gameTimestamp;gameImageSize=$gameImageSize;serverUsableSlots=500000;files=@(Get-ChildItem -LiteralPath $build -File | Where-Object Extension -in @('.exe','.dll') | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $build 'build-receipt.json') -Encoding utf8
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
