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
    $flags=@('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2',"/I$repo/source/profiles","/Fo$output/")
    $dll=Join-Path $output 'LoaderFixture.dll'
    & $msvc.Cl @flags /LD (Join-Path $PSScriptRoot 'LoaderFixture.cpp') (Join-Path $repo 'source/launch/startup_gate/LoaderSafety.cpp') "/Fe$dll" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Loader fixture compilation failed.' }
    $runner=Join-Path $output 'LoaderRunner.exe'
    & $msvc.Cl @flags (Join-Path $PSScriptRoot 'LoaderRunner.cpp') "/Fe$runner" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Loader runner compilation failed.' }
    Invoke-Windows $runner $dll | Tee-Object -FilePath (Join-Path $output 'trace.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Loader safety fixture failed. See trace.txt.' }
    $files=@($dll,$runner,(Join-Path $output 'trace.txt'),(Join-Path $repo 'source/launch/startup_gate/LoaderSafety.cpp'),(Join-Path $PSScriptRoot 'LoaderFixture.cpp'),(Join-Path $PSScriptRoot 'LoaderRunner.cpp'),(Join-Path $PSScriptRoot 'failure-cases.txt'))
    @{passed=$true;scope='Owned loader fixture only. No game launch.';files=@($files | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $output 'result.json')
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
