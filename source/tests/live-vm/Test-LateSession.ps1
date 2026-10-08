#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Python,[Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..'); $output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep late enrollment artifacts outside the repository.' }
if(Test-Path -LiteralPath $output) { throw 'Use a new late enrollment directory.' }
New-Item -ItemType Directory -Path "$output/bin" | Out-Null
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE; $savedLib=$env:LIB
$owned=Join-Path $repo 'source/tests/vm'
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $compiler=Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MD /LD "$owned/EnhancedOverlayHelper.cpp" "/Fe:$output/bin/Bo3EnhancedHelper.dll" "/Fo:$output/bin/Helper.obj" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned late enrollment helper compilation failed.' }
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MD "$owned/EnhancedOverlayFixture.cpp" "/Fe:$output/bin/EnhancedOverlayFixture.exe" "/Fo:$output/bin/Fixture.obj" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned late enrollment fixture compilation failed.' }
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
$paths=@(Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName)+@("$owned/EnhancedOverlayHelper.cpp","$owned/EnhancedOverlayFixture.cpp","$owned/Verify-EnhancedSession.py",(Join-Path $repo 'source/live/vm/enhanced_session.py'),(Join-Path $repo 'source/live/vm/profile.py'),(Join-Path $repo 'source/live/vm/snapshot.py'),(Join-Path $repo 'source/live/vm/latest_state.py'),(Join-Path $repo 'source/live/windows_process.py'),(Join-Path $repo 'source/launch/enhanced/PhysicalPath.ps1'))
@{scope='Owned late receipt VM enrollment only. No game launch.';sources=@($paths | Get-FileHash | Select-Object Path,Hash)} |
    ConvertTo-Json -Depth 5 | Set-Content "$output/build-receipt.json" -Encoding utf8
& $Python -B (Join-Path $PSScriptRoot 'Verify-LateSession.py') --fixture "$output/bin/EnhancedOverlayFixture.exe" --output $output
if($LASTEXITCODE -ne 0) { throw 'Late receipt enrollment E2E failed.' }
