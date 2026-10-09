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
    $fixture=Join-Path $output 'ImageFixture.exe'
    $sources=@((Join-Path $PSScriptRoot 'ImageFixture.cpp'),(Join-Path $repo 'source/patches/early_integrity/ImageMemory.cpp'),(Join-Path $repo 'source/patches/vm_startup/PausedPatch.cpp'))
    & $msvc.Cl /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 @sources "/Fo$output/" "/Fe$fixture" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Image memory fixture compilation failed.' }
    Invoke-Windows $fixture | Tee-Object -FilePath (Join-Path $output 'trace.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Image memory fixture failed. See trace.txt.' }
    $files=@($sources)+@($fixture,(Join-Path $output 'trace.txt'),(Join-Path $PSScriptRoot 'failure-cases.txt'))
    @{passed=$true;scope='Owned executable image only. No game launch.';files=@($files | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $output 'result.json')
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
