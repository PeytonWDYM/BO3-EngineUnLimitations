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
    $fixture=Join-Path $PSScriptRoot 'LoadContextFixture.cpp'
    $implementation=Join-Path $PSScriptRoot '../../patches/actor_pool/LoadContext.cpp'
    $header=Join-Path $PSScriptRoot '../../patches/actor_pool/LoadContext.h'
    $binary=Join-Path $target 'LoadContextFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MT /std:c++20 /O2 $fixture $implementation "/Fe:$binary" "/Fo:$target/" /link /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) {throw 'The actor context build failed.'}
    & $binary (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) {throw 'The actor root/context fixture failed.'}
    $paths=@($fixture,$implementation,$header,$PSCommandPath,$binary,(Join-Path $target 'result.json'))
    $hashes=foreach($path in $paths){Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path,Hash}
    @{passed=$true;scope='Owned actor root/context admission and authored native callback endpoints. Game root binding remains unverified.';files=@($hashes)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
