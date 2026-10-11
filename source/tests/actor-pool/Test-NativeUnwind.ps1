#Requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$Manifest,
    [Parameter(Mandatory)][string]$Executable,
    [string]$Python = 'python',
    [switch]$IncludeTemporalRestore,
    [switch]$ClientSnapshots,
    [switch]$ClientAllocation,
    [ValidateSet(300,500)][int]$Actors=300
)
$ErrorActionPreference = 'Stop'
$target = [IO.Path]::GetFullPath($Output)
if (@($ClientSnapshots,$ClientAllocation,$IncludeTemporalRestore).Where({$_}).Count -gt 1) { throw 'Select one native unwind comparison.' }
$generator = if ($ClientSnapshots) { 'Test-ClientSnapshotUnwind.py' } elseif ($ClientAllocation) { 'Test-ClientAllocationUnwind.py' } else { 'Test-NativeUnwind.py' }
$arguments = @('-B', (Join-Path $PSScriptRoot $generator), '--module', $Manifest, '--executable', $Executable, '--output', $target)
if (-not $ClientAllocation) {$arguments += @('--actors',$Actors)}
if ($IncludeTemporalRestore) { $arguments += '--include-temporal-restore' }
& $Python @arguments
if ($LASTEXITCODE -ne 0) { throw 'The guarded native-unwind export failed.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler = Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk = Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude, $savedLib = $env:INCLUDE, $env:LIB
try {
    $env:INCLUDE = "$($compiler.FullName)/include;$sdkRoot/Include/$($sdk.Name)/um;$sdkRoot/Include/$($sdk.Name)/shared;$sdkRoot/Include/$($sdk.Name)/ucrt"
    $env:LIB = "$($compiler.FullName)/lib/x64;$sdkRoot/Lib/$($sdk.Name)/um/x64;$sdkRoot/Lib/$($sdk.Name)/ucrt/x64"
    $fixture = Join-Path $PSScriptRoot 'NativeUnwindFixture.cpp'
    $binary = Join-Path $target 'NativeUnwindFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MT /std:c++20 /O2 $fixture "/Fe:$binary" "/Fo:$target/" /link /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The Windows native-unwind fixture build failed.' }
    & $binary (Join-Path $target 'native-unwind.bin') | Tee-Object -FilePath (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) { throw 'The Windows native-unwind fixture failed.' }
    $paths = @($fixture, $PSCommandPath, $binary, (Join-Path $target 'input-receipt.json'), (Join-Path $target 'result.json'))
    $hashes = foreach ($path in $paths) { Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path, Hash }
    @{passed = $true; scope = 'Owned original-frame comparison and Windows virtual unwinding. Handler dispatch and game registration remain unverified.'; files = @($hashes)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
