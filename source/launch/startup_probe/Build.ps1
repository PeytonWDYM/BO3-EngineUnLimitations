#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$DetoursRoot,
    [Parameter(Mandatory)][string]$Python,[string]$CallerCapture,[string]$Fixture,[switch]$RefuseFixtureIdentity)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..'); $output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep probe builds outside the repository.' }
if(Test-Path -LiteralPath $output) { throw 'Use a new probe directory.' }
if([bool]$CallerCapture -eq [bool]$Fixture -or ($RefuseFixtureIdentity -and !$Fixture)) { throw 'Select one fixed captured or owned caller profile.' }
$DetoursRoot=PhysicalPath $DetoursRoot
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no) -or
    (Get-FileHash -LiteralPath $library).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC') { throw 'Use the pinned unchanged official Detours library.' }
New-Item -ItemType Directory -Path $output | Out-Null
$profileArguments=@('--output',"$output/ProbeProfile.h")
if($Fixture) {
    $profileArguments+=@('--fixture',$Fixture)
    if($RefuseFixtureIdentity) { $profileArguments+='--refuse-fixture-identity' }
} else {
    Copy-Item -LiteralPath $CallerCapture -Destination "$output/captured-caller.json"
    $profileArguments+=@('--capture',"$output/captured-caller.json")
}
& $Python -B (Join-Path $PSScriptRoot 'Generate-Profile.py') @profileArguments
if($LASTEXITCODE -ne 0) { throw 'Probe caller profile generation failed.' }
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
    $sources=@('Helper.cpp','Observation.cpp') | ForEach-Object { Join-Path $PSScriptRoot $_ }
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 /LD "/I$output" "/I$DetoursRoot/include" @sources $library "/Fo:$output/" "/Fe:$output/Bo3EnhancedHelper.dll" /link "/DEF:$PSScriptRoot/Helper.def" /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Probe helper compilation failed.' }
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
Copy-Item -LiteralPath (Join-Path $DetoursRoot 'LICENSE.md') -Destination "$output/Detours-LICENSE.md"
$paths=@(Get-ChildItem -LiteralPath $PSScriptRoot -File | ForEach-Object FullName)+@("$output/ProbeProfile.h","$output/caller-profile-receipt.json",$library,(Join-Path $DetoursRoot 'include/detours.h'),(Join-Path $repo 'source/launch/enhanced/Boot.h'),(Join-Path $repo 'source/launch/enhanced/PhysicalPath.ps1'))
if(!$Fixture) { $paths+="$output/captured-caller.json" }
@{scope='Observation-only API probe. Separate private helper. No pool, codec, DR or protected-check writes.';
    helperSha256=(Get-FileHash "$output/Bo3EnhancedHelper.dll").Hash.ToLowerInvariant();
    fixture=[bool]$Fixture; sources=@($paths | Get-FileHash | Select-Object Path,Hash)} |
    ConvertTo-Json -Depth 6 | Set-Content "$output/build-receipt.json" -Encoding utf8
