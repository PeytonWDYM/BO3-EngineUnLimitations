#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Python,[Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private enrollment output.'}
New-Item -ItemType Directory -Path "$output/bin" | Out-Null
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE;$savedLib=$env:LIB
$owned=Join-Path $repo 'source/tests/vm'
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $compiler=Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MD /LD "$owned/EnhancedOverlayHelper.cpp" "/Fe:$output/bin/Bo3EnhancedHelper.dll" "/Fo:$output/bin/Helper.obj" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned enrollment helper build failed.'}
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MD "$owned/EnhancedOverlayFixture.cpp" "/Fe:$output/bin/EnhancedOverlayFixture.exe" "/Fo:$output/bin/Fixture.obj" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned enrollment fixture build failed.'}
}finally{$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
$sources=@("$repo/source/live/vm/enhanced_session.py","$repo/source/live/vm/profile.py","$repo/source/live/vm/snapshot.py",
    "$repo/source/live/windows_process.py","$owned/Verify-EnhancedSession.py","$owned/EnhancedOverlayHelper.cpp","$owned/EnhancedOverlayFixture.cpp",
    "$repo/source/tests/live-vm/Verify-LateSession.py") + @(Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName)
@{sources=@($sources | Get-FileHash | Select-Object Path,Hash);scope='Owned enrollment fixture only'} |
    ConvertTo-Json -Depth 5 | Set-Content "$output/build-receipt.json" -Encoding utf8
& $Python -B (Join-Path $PSScriptRoot 'Verify.py') --fixture "$output/bin/EnhancedOverlayFixture.exe" --output $output
if($LASTEXITCODE -ne 0){throw 'Owned job enrollment E2E failed.'}
$snapshots=Join-Path $output 'source-snapshot'
New-Item -ItemType Directory -Path $snapshots | Out-Null
foreach($source in $sources){Copy-Item -LiteralPath $source -Destination (Join-Path $snapshots ([IO.Path]::GetFileName($source)))}
