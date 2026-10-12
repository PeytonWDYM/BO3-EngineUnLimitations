#Requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$NativeBuild,
    [Parameter(Mandatory)][string]$ClientSpans,
    [Parameter(Mandatory)][string]$ServerSpans
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$target = [IO.Path]::GetFullPath($Output)
if ((Test-Path -LiteralPath $target) -or $target.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or $target.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Use a new output folder outside Git.' }
$build = (Resolve-Path -LiteralPath $NativeBuild).Path
$buildReceipt = Get-Content -LiteralPath (Join-Path $build 'build-receipt.json') -Raw | ConvertFrom-Json
if ($buildReceipt.clientTotal -ne 250001 -or $buildReceipt.nativeEdits -ne 372 -or $buildReceipt.actorCapacity -ne 500 -or $buildReceipt.sentientCapacity -ne 540 -or $buildReceipt.actorRuntimeFunctions -ne 2465 -or $buildReceipt.serverUsableSlots -ne 500000 -or $buildReceipt.pendingCallbacksPerLocalClient -ne 8192 -or $buildReceipt.clientfieldCounters -ne 8192) { throw 'Use the complete actor500 native build. This fixture checks only VM and migration admission.' }
if ((Get-FileHash -LiteralPath $ClientSpans).Hash -ne 'A5E603E7B0A3519797262C86A91248A985596B6DF5C719EA14E04D5964FBF50C' -or (Get-FileHash -LiteralPath $ServerSpans).Hash -ne '2EC3591846D8710A920E0443F4A808AE1B7FDA5D7DE58BDBC49FF140761B9836') { throw 'Use the pinned client and normalized server guard spans.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler = Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk = Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude, $savedLib = $env:INCLUDE, $env:LIB
New-Item -ItemType Directory -Path $target | Out-Null
try {
    $env:INCLUDE = "$($compiler.FullName)/include;$sdkRoot/Include/$($sdk.Name)/um;$sdkRoot/Include/$($sdk.Name)/shared;$sdkRoot/Include/$($sdk.Name)/ucrt"
    $env:LIB = "$($compiler.FullName)/lib/x64;$sdkRoot/Lib/$($sdk.Name)/um/x64;$sdkRoot/Lib/$($sdk.Name)/ucrt/x64"
    $flags = @('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2',"/I$repo","/I$build","/I$repo/source/launch/enhanced")
    $files = @('source/tests/client-vm/ClientAdmissionFixture.cpp','source/launch/enhanced/ClientProfile.cpp','source/launch/enhanced/GameProfile.cpp','source/launch/preentry/Identity.cpp','source/patches/vm_startup/NativePlan.cpp','source/patches/vm_migration/MigrationPlan.cpp') | ForEach-Object {Join-Path $repo $_}
    $binary = Join-Path $target 'ClientAdmissionFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') @flags @files "/Fo:$target/" "/Fe:$binary" /link bcrypt.lib /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The native client admission fixture build failed.' }
    $unknown = Join-Path $target 'unknown.bin'
    [IO.File]::WriteAllText($unknown, 'Owned unknown executable fixture. No game code.')
    & $binary $ClientSpans $ServerSpans $unknown | Tee-Object -FilePath (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) { throw 'The native client admission fixture failed.' }
    $paths = @($files) + @($binary,$PSCommandPath,$ClientSpans,$ServerSpans,(Join-Path $build 'GameManifest.h'),(Join-Path $build 'ClientManifest.h'),(Join-Path $target 'result.json'))
    $hashes = foreach ($path in $paths) {Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path,Hash}
    @{passed=$true; scope='Owned stopped-read VM and migration fixture with exact captured guards. Actor admission is outside this fixture. No process writes or game launch.'; files=@($hashes)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
