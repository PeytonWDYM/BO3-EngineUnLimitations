#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$ProductionBuild,
    [Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..'); $output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep control E2E outside the repository.' }
if(Test-Path -LiteralPath $output) { throw 'Use a new control E2E directory.' }
# The production builder verifies pinned Detours and unchanged release helper before any child.
$productionBin=Join-Path $output 'production'
& (Join-Path $repo 'source/launch/enhanced/Build-StartupDiagnostic.ps1') -OutputDirectory $productionBin -ProductionBuild $ProductionBuild -DetoursRoot $DetoursRoot -Python $Python
$bin=Join-Path $output 'owned'; New-Item -ItemType Directory -Path $bin | Out-Null
Copy-Item -LiteralPath (Join-Path $productionBin 'Bo3EnhancedHelper.dll') -Destination $bin
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE; $savedLib=$env:LIB
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $target=Join-Path $bin 'VmStartupControlTarget.exe'
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 (Join-Path $PSScriptRoot 'StartupControlTarget.cpp') "/Fo:$bin/StartupControlTarget.obj" "/Fe:$target" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned control target compilation failed.' }
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
$repoLiteral=$repo.Replace('\','\\')
@('#pragma once',"constexpr wchar_t kRepositoryRoot[]=L`"$repoLiteral`";", "constexpr char kGameHash[]=`"$((Get-FileHash -LiteralPath $target).Hash.ToLowerInvariant())`";",
    "constexpr char kHelperHash[]=`"$((Get-FileHash -LiteralPath (Join-Path $bin 'Bo3EnhancedHelper.dll')).Hash.ToLowerInvariant())`";") | Set-Content -LiteralPath (Join-Path $bin 'BuildIdentity.h') -Encoding ascii
& $Python -B (Join-Path $PSScriptRoot 'Control-Profile.py') --helper (Join-Path $bin 'Bo3EnhancedHelper.dll') --fixture $target --output (Join-Path $bin 'ControlProfile.h')
if($LASTEXITCODE -ne 0) { throw 'Owned control profile generation failed.' }
& (Join-Path $PSScriptRoot 'Compile-StartupControl.ps1') -OutputDirectory $bin -DetoursRoot $DetoursRoot
& $Python -B (Join-Path $PSScriptRoot 'Verify-StartupControl.py') --bin $bin --production $productionBin --output $output
if($LASTEXITCODE -ne 0) { throw 'Owned startup control E2E failed.' }
