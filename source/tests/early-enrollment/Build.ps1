#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private owned output directory.'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE;$savedLib=$env:LIB
try {
    $env:INCLUDE="$compiler/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compiler/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    New-Item -ItemType Directory -Path $output | Out-Null
    $tool=Join-Path $compiler 'bin/Hostx64/x64/cl.exe'
    & $tool /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 /LD "$repo/source/tests/vm/EnhancedOverlayHelper.cpp" "/Fo:$output/Helper.obj" "/Fe:$output/Bo3EnhancedHelper.dll" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned helper compilation failed.'}
    & $tool /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 "$PSScriptRoot/Target.cpp" "/Fo:$output/Target.obj" "/Fe:$output/EarlyEnrollmentFixture.exe" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned target compilation failed.'}
} finally {$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
& $Python -B "$PSScriptRoot/Verify.py" --output "$output/e2e" --fixture "$output/EarlyEnrollmentFixture.exe"
if($LASTEXITCODE -ne 0){throw 'Owned early checksum enrollment failed.'}
$paths=@(Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName)+@(Get-ChildItem "$repo/source/live/vm" -File | ForEach-Object FullName)+@("$output/Bo3EnhancedHelper.dll","$output/EarlyEnrollmentFixture.exe")
@{passed=$true;files=@($paths | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 5 | Set-Content "$output/build-receipt.json" -Encoding utf8
