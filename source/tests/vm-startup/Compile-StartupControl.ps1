#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$DetoursRoot)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..')
$OutputDirectory=PhysicalPath $OutputDirectory
if($OutputDirectory.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $OutputDirectory.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep diagnostic builds outside the repository.' }
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(!$installation) { throw 'Install Visual C++ x64 build tools.' }
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE; $savedLib=$env:LIB
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $sources=@('source/launch/enhanced/StartupDiagnostic.cpp','source/launch/enhanced/StartupControl.cpp','source/launch/enhanced/StartupObservation.cpp','source/launch/enhanced/StartupPassive.cpp','source/launch/enhanced/SteamContext.cpp','source/launch/preentry/Identity.cpp') | ForEach-Object { Join-Path $repo $_ }
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 "/I$OutputDirectory" "/I$DetoursRoot/include" @sources (Join-Path $DetoursRoot 'lib.X64/detours.lib') "/Fo:$OutputDirectory/" "/Fe:$OutputDirectory/BO3-Startup-Control.exe" /link bcrypt.lib /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Startup control compilation failed.' }
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
