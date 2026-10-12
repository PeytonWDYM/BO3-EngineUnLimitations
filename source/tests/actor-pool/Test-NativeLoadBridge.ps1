#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($Output)
$lab=[IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.codex/labs/bo3-engine'))
if (-not $target.StartsWith($lab+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $target)) {throw 'Use a new private BO3 lab directory.'}
New-Item -ItemType Directory -Path $target | Out-Null
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler=Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude,$savedLib=$env:INCLUDE,$env:LIB
try {
    $env:INCLUDE="$($compiler.FullName)/include;$sdkRoot/Include/$($sdk.Name)/um;$sdkRoot/Include/$($sdk.Name)/shared;$sdkRoot/Include/$($sdk.Name)/ucrt"
    $env:LIB="$($compiler.FullName)/lib/x64;$sdkRoot/Lib/$($sdk.Name)/um/x64;$sdkRoot/Lib/$($sdk.Name)/ucrt/x64"
    $patches=Join-Path $PSScriptRoot '../../patches/actor_pool'
    $fixture=Join-Path $PSScriptRoot 'NativeLoadBridgeFixture.cpp'
    $implementation=Join-Path $patches 'NativeLoadBridge.cpp'
    $context=Join-Path $patches 'LoadContext.cpp'
    $assembly=Join-Path $patches 'ReadReentries.asm'
    $object=Join-Path $target 'ReadReentries.obj'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/ml64.exe') /nologo /c "/Fo$object" $assembly 2>&1 | Tee-Object -FilePath (Join-Path $target 'assembly-build.txt')
    if ($LASTEXITCODE -ne 0) {throw 'The actor read reentries did not assemble.'}
    $binary=Join-Path $target 'NativeLoadBridgeFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MT /std:c++20 /O2 $fixture $implementation $context $object "/Fe:$binary" "/Fo:$target/" /link /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) {throw 'The native actor load bridge build failed.'}
    & $binary (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) {throw 'The owned native actor load bridge fixture failed.'}
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/dumpbin.exe') /DISASM /RELOCATIONS /UNWINDINFO $object | Set-Content -LiteralPath (Join-Path $target 'read-reentries.txt')
    $paths=@($fixture,$implementation,$context,$assembly,(Join-Path $patches 'NativeLoadBridge.h'),(Join-Path $patches 'ActorRecord.h'),(Join-Path $patches 'LoadContext.h'),(Join-Path $PSScriptRoot 'native-load-failure-cases.txt'),$PSCommandPath,$object,$binary,(Join-Path $target 'result.json'),(Join-Path $target 'read-reentries.txt'))
    $hashes=foreach($path in $paths){Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path,Hash}
    @{passed=$true;scope='Owned complete actor allocations, authored callbacks, deferred whole loads, scoped Windows threads, exact history conversion, and assembled reentries. Game, peer, and Proton behavior remain unverified.';files=@($hashes)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
