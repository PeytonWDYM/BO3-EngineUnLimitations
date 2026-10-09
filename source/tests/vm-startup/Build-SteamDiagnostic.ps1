#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$output=PhysicalPath $OutputDirectory
if ($output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or $output.Equals($repo,[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep owned outputs outside the repository.' }
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory.' }
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE
$savedLib=$env:LIB
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    New-Item -ItemType Directory -Path $output | Out-Null
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 (Join-Path $PSScriptRoot 'SteamDiagnosticArgv.cpp') "/Fo:$output/owned.obj" "/Fe:$output/OwnedSteamArgv.exe" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Owned argv target compilation failed.' }
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
& $Python (Join-Path $PSScriptRoot 'Test-SteamDiagnostic.py') --output "$output/e2e" --target "$output/OwnedSteamArgv.exe" --pwsh (Join-Path $PSHOME 'pwsh.exe')
if ($LASTEXITCODE -ne 0) { throw 'Owned Steam diagnostic E2E failed.' }
