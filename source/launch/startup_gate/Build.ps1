#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$DetoursRoot,
    [Parameter(Mandatory)][string]$Python,[string]$CallerCapture,[string]$Fixture,[switch]$MissingLoaderQuery,[switch]$MissingEntryAnchor)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..'); $output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep gate builds outside the repository.' }
if(Test-Path -LiteralPath $output) { throw 'Use a new gate build directory.' }
if([bool]$CallerCapture -eq [bool]$Fixture -or (($MissingLoaderQuery -or $MissingEntryAnchor) -and !$Fixture)) { throw 'Select one captured or fixed owned caller profile.' }
$DetoursRoot=PhysicalPath $DetoursRoot
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no) -or
    (Get-FileHash -LiteralPath $library).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC') { throw 'Use the pinned unchanged official Detours library.' }
New-Item -ItemType Directory -Path $output | Out-Null
$profileArguments=@('--output',"$output/ProbeProfile.h")
if($Fixture) { $profileArguments+=@('--fixture',$Fixture) }
else { Copy-Item -LiteralPath $CallerCapture -Destination "$output/captured-caller.json"; $profileArguments+=@('--capture',"$output/captured-caller.json") }
$generator=Join-Path $repo 'source/launch/startup_probe/Generate-Profile.py'
& $Python -B $generator @profileArguments
if($LASTEXITCODE -ne 0) { throw 'Fixed gate caller profile generation failed.' }
$deadline=if($Fixture) {1000} else {30000}
$query=if($MissingLoaderQuery) {'OwnedMissingLoaderQuery'} else {'RtlIsThreadWithinLoaderCallout'}
$anchor=if($MissingEntryAnchor) {'OwnedMissingEntryAnchor'} else {'BaseThreadInitThunk'}
@('#pragma once',"constexpr DWORD kGateDeadlineMs=$($deadline)u;", "constexpr char kLoaderQueryName[]=`"$query`";", "constexpr char kEntryAnchorName[]=`"$anchor`";") | Set-Content "$output/GateProfile.h" -Encoding ascii
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE; $savedLib=$env:LIB
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $sources=@('Helper.cpp','Admission.cpp','Gate.cpp','NativeEntry.cpp') | ForEach-Object { Join-Path $PSScriptRoot $_ }
    $sources+=Join-Path $repo 'source/launch/startup_probe/Observation.cpp'
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 /LD "/I$output" "/I$DetoursRoot/include" @sources $library OneCore.lib "/Fo:$output/" "/Fe:$output/Bo3StartupGate.dll" /link "/DEF:$PSScriptRoot/Helper.def" /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Cooperative gate helper compilation failed.' }
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
Copy-Item -LiteralPath (Join-Path $DetoursRoot 'LICENSE.md') -Destination "$output/Detours-LICENSE.md"
$paths=@(Get-ChildItem -LiteralPath $PSScriptRoot -File | ForEach-Object FullName)+@("$output/ProbeProfile.h","$output/GateProfile.h","$output/caller-profile-receipt.json",$generator,$library,(Join-Path $DetoursRoot 'include/detours.h'),(Join-Path $repo 'source/launch/enhanced/Boot.h'),(Join-Path $repo 'source/launch/enhanced/PhysicalPath.ps1'),(Join-Path $repo 'source/launch/startup_probe/Observation.h'),(Join-Path $repo 'source/launch/startup_probe/Observation.cpp'))
$paths+=Join-Path $sdkRoot "Lib/$sdk/um/x64/OneCore.lib"
if(!$Fixture) { $paths+="$output/captured-caller.json" }
@{scope='Cooperative primary-thread CRT gate only. No native/VM/DR edits or game launch.';
    helperSha256=(Get-FileHash "$output/Bo3StartupGate.dll").Hash.ToLowerInvariant(); fixture=[bool]$Fixture;
    deadlineMs=$deadline; sources=@($paths | Get-FileHash | Select-Object Path,Hash)} |
    ConvertTo-Json -Depth 6 | Set-Content "$output/build-receipt.json" -Encoding utf8
