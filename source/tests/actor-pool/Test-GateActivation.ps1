#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($Output)
$lab=[IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.codex/labs/bo3-engine'))
if (-not $target.StartsWith($lab+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $target)) {throw 'Use a new private BO3 lab directory.'}
New-Item -ItemType Directory -Path $target | Out-Null
@('#pragma once','#include <Windows.h>','constexpr DWORD kCallerRva=0x1000,kReturnRva=0x102C,kCrtReturnRva=0x2000,kWrapperCallerDelta=160;','constexpr unsigned char kCallerBytes[44]={0x90};') | Set-Content -LiteralPath (Join-Path $target 'ProbeProfile.h') -Encoding ascii
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler=Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude,$savedLib=$env:INCLUDE,$env:LIB
try {
    $env:INCLUDE="$($compiler.FullName)/include;$sdkRoot/Include/$($sdk.Name)/um;$sdkRoot/Include/$($sdk.Name)/shared;$sdkRoot/Include/$($sdk.Name)/ucrt"
    $env:LIB="$($compiler.FullName)/lib/x64;$sdkRoot/Lib/$($sdk.Name)/um/x64;$sdkRoot/Lib/$($sdk.Name)/ucrt/x64"
    $fixture=Join-Path $PSScriptRoot 'GateActivationFixture.cpp'
    $gate=Join-Path $PSScriptRoot '../../launch/startup_gate/Gate.cpp'
    $binding=Join-Path $PSScriptRoot '../../patches/actor_pool/RuntimeBinding.cpp'
    $binary=Join-Path $target 'GateActivationFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MT /std:c++20 /O2 "/I$target" $fixture $gate $binding "/Fe:$binary" "/Fo:$target/" /link /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) {throw 'The gate activation build failed.'}
    & $binary success (Join-Path $target 'success.json')
    if ($LASTEXITCODE -ne 0) {throw 'The gate returned without actor registration.'}
    & $binary refuse (Join-Path $target 'refuse.json')
    if ([uint32]([int64]$LASTEXITCODE -band 0xFFFFFFFFL) -ne 0xE0427606L -or (Test-Path -LiteralPath (Join-Path $target 'refuse.json'))) {throw 'Failed actor registration returned to its native caller.'}
    $paths=@($fixture,$gate,$binding,$PSCommandPath,$binary,(Join-Path $target 'ProbeProfile.h'),(Join-Path $target 'success.json'),(Join-Path $PSScriptRoot '../../launch/startup_gate/GateContract.h'),(Join-Path $PSScriptRoot '../../patches/actor_pool/RuntimeBinding.h'))
    @{passed=$true;registrationFailureExit='0xe0427606';scope='Actual gate and runtime callback with authored admission/observation and owned memory. No game caller or game registration.';files=@($paths | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
}finally {$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
