#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($Output)
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
if ((Test-Path -LiteralPath $target) -or $target.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Use a new output directory outside the repository.'
}
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
    $fixture=Join-Path $PSScriptRoot 'GameExitFixture.cpp'
    $binary=Join-Path $target 'GameExitFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MT /std:c++20 /O2 $fixture "/Fe:$binary" "/Fo:$target/" /link /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) {throw 'The Windows exit fixture build failed.'}
    & $binary $target | Tee-Object -FilePath (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) {throw 'The Windows exit fixture failed.'}
    foreach ($code in @(0,37)) {
        $receipt=Get-Content -LiteralPath (Join-Path $target "$code-exit.json") -Raw | ConvertFrom-Json
        if (!$receipt.exited -or $receipt.exitCode -ne $code -or $receipt.stage -ne 'exited' -or $receipt.editsWritten -ne 1158) {
            throw 'The persisted child exit receipt differs from the selected exit.'
        }
    }
    $paths=@($fixture,$PSCommandPath,$binary,(Join-Path $PSScriptRoot '../../launch/early_startup/GameLifetime.h'),
        (Join-Path $target 'result.json'),(Join-Path $target '0-exit.json'),(Join-Path $target '37-exit.json'))
    $hashes=foreach ($path in $paths) {Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path,Hash}
    @{passed=$true;scope='Owned Windows children and final receipt persistence. No game launch.';files=@($hashes)} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {
    $env:INCLUDE=$savedInclude;$env:LIB=$savedLib
}
