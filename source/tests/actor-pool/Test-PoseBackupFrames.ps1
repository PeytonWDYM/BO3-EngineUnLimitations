#Requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$Manifest,
    [Parameter(Mandatory)][string]$Executable,
    [string]$Python = 'python',
    [switch]$Expanded
)
$ErrorActionPreference = 'Stop'
$target = [IO.Path]::GetFullPath($Output)
$exportArguments = @('--module', $Manifest, '--executable', $Executable, '--output', $target)
if ($Expanded) { $exportArguments += '--expanded' }
& $Python -B (Join-Path $PSScriptRoot 'Test-PoseBackupFrames.py') @exportArguments
if ($LASTEXITCODE -ne 0) { throw 'The guarded pose frame export failed.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler = Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk = Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude, $savedLib = $env:INCLUDE, $env:LIB
try {
    $env:INCLUDE = "$($compiler.FullName)/include;$sdkRoot/Include/$($sdk.Name)/um;$sdkRoot/Include/$($sdk.Name)/shared;$sdkRoot/Include/$($sdk.Name)/ucrt"
    $env:LIB = "$($compiler.FullName)/lib/x64;$sdkRoot/Lib/$($sdk.Name)/um/x64;$sdkRoot/Lib/$($sdk.Name)/ucrt/x64"
    $fixture = Join-Path $PSScriptRoot 'PoseBackupFrameFixture.cpp'
    $binary = Join-Path $target 'PoseBackupFrameFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MT /std:c++20 /O2 $fixture "/Fe:$binary" "/Fo:$target/" /link /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The Windows pose frame fixture build failed.' }
    $input = Join-Path $target 'pose-backup-frames.bin'
    & $binary $input correct | Tee-Object -FilePath (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) { throw 'The Windows pose frame fixture failed.' }
    $refusals = foreach ($frame in 0..5) {
        & $binary $input "old-cookie-$frame"
        if ($LASTEXITCODE -ne 23) { throw "A stale pose cookie escaped refusal in frame $frame`: $LASTEXITCODE" }
        @{frame = $frame; staleCookieExitCode = $LASTEXITCODE}
    }
    @{passed = $true; refusals = @($refusals)} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $target 'refusal.json')
    $paths = @($fixture, $PSCommandPath, $binary, (Join-Path $PSScriptRoot 'Test-PoseBackupFrames.py'),
        (Join-Path $PSScriptRoot 'pose-backup-frame-failure-cases.txt'), (Join-Path $target 'input-receipt.json'),
        (Join-Path $target 'result.json'), (Join-Path $target 'refusal.json'))
    $hashes = foreach ($path in $paths) { Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path, Hash }
    @{passed = $true; scope = 'Six owned Windows pose frame shells, exact GS/EH handlers and cleanup funclets with fixture CRT and authored endpoints. Game behavior remains unverified.'; files = @($hashes)} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
