#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Output,[Parameter(Mandatory)][string]$NativeBuild,[Parameter(Mandatory)][string]$Spans)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$target=[IO.Path]::GetFullPath($Output)
if ((Test-Path -LiteralPath $target) -or $target.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $target.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'Use a new output folder outside Git.'}
$build=(Resolve-Path -LiteralPath $NativeBuild).Path
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler=Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude,$savedLib=$env:INCLUDE,$env:LIB
New-Item -ItemType Directory -Path $target | Out-Null
try {
    $env:INCLUDE="$($compiler.FullName)/include;$sdkRoot/Include/$($sdk.Name)/um;$sdkRoot/Include/$($sdk.Name)/shared;$sdkRoot/Include/$($sdk.Name)/ucrt"
    $env:LIB="$($compiler.FullName)/lib/x64;$sdkRoot/Lib/$($sdk.Name)/um/x64;$sdkRoot/Lib/$($sdk.Name)/ucrt/x64"
    $flags=@('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2',"/I$repo","/I$build","/I$repo/source/launch/enhanced")
    $files=@('source/tests/clientfields/PendingNativeFixture.cpp','source/patches/clientfields/PendingProfile.cpp','source/patches/clientfields/PendingStorage.cpp','source/patches/vm_startup/PausedPatch.cpp','source/launch/enhanced/GameProfile.cpp','source/launch/preentry/Identity.cpp') | ForEach-Object {Join-Path $repo $_}
    $binary=Join-Path $target 'PendingNativeFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') @flags @files "/Fo:$target/" "/Fe:$binary" /link bcrypt.lib /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) {throw 'The callback native fixture build failed.'}
    & $binary $Spans | Tee-Object -FilePath (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) {throw 'The callback native fixture failed.'}
    $paths=@($files)+@($binary,$PSCommandPath,$Spans,(Join-Path $build 'PendingManifest.h'),(Join-Path $target 'result.json'))
    @{passed=$true;gameLaunches=0;files=@($paths | ForEach-Object {Get-FileHash -LiteralPath $_ | Select-Object Path,Hash})} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
