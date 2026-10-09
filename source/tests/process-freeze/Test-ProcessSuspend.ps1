#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../../../scripts/release/Platform.ps1')
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-WithinPath $output $repo) { throw 'Keep fixture artifacts outside the repository.' }
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory.' }
New-Item -ItemType Directory -Path $output | Out-Null
$msvc = Get-MsvcToolchain
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
try {
    if ($msvc.Include) { $env:INCLUDE = $msvc.Include; $env:LIB = $msvc.Lib }
    $fixture = Join-Path $output 'SuspendFixture.exe'
    $sources = @((Join-Path $PSScriptRoot 'SuspendFixture.cpp'), (Join-Path $repo 'source/launch/process_freeze/NativeJobFreeze.cpp'), (Join-Path $repo 'source/launch/process_freeze/NativeState.cpp'))
    & $msvc.Cl /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 /DBO3_PROCESS_SUSPEND_TEST @sources "/Fo$output/" "/Fe$fixture" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The suspend fixture build failed.' }
    Invoke-Windows $fixture | Tee-Object -FilePath (Join-Path $output 'trace.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The suspend fixture failed. See trace.txt.' }
    $files = @($sources) + @((Join-Path $PSScriptRoot 'failure-cases.txt'), $fixture, (Join-Path $output 'trace.txt'))
    $hashes = foreach ($file in $files) { Get-FileHash -LiteralPath $file -Algorithm SHA256 | Select-Object Path, Hash }
    @{passed = $true; files = @($hashes); scope = 'Owned child processes only. No game launch.'} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $output 'result.json')
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
