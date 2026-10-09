#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../../scripts/release/Platform.ps1')
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$output=[IO.Path]::GetFullPath($OutputDirectory)
if ((Test-WithinPath $output $repo) -or (Test-Path -LiteralPath $output)) { throw 'Use a new fixture folder outside the repository.' }
New-Item -ItemType Directory -Path $output | Out-Null
$msvc=Get-MsvcToolchain
$savedInclude=$env:INCLUDE; $savedLib=$env:LIB
try {
    if ($msvc.Include) { $env:INCLUDE=$msvc.Include; $env:LIB=$msvc.Lib }
    $fixture=Join-Path $output 'IntroFixture.exe'
    $source=Join-Path $PSScriptRoot 'IntroFixture.cpp'
    & $msvc.Cl /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 $source "/Fo$output/" "/Fe$fixture" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Intro fixture compilation failed.' }
    Invoke-Windows $fixture | Tee-Object -FilePath (Join-Path $output 'trace.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Intro fixture failed. See trace.txt.' }
    @{passed=$true;scope='Pure startup intro admission and edit fixture. No game launch.';files=@((Get-Item $source),(Get-Item $fixture),(Get-Item (Join-Path $repo 'source/patches/startup_intro/Plan.h'))) | Get-FileHash | Select-Object Path,Hash} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $output 'result.json')
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
