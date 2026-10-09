#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$DetoursRoot,
    [Parameter(Mandatory)][string]$Python,[Parameter(Mandatory)][string]$CallerCapture)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..'); $output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep gate E2E outside the repository.' }
if(Test-Path -LiteralPath $output) { throw 'Use a new gate E2E directory.' }
New-Item -ItemType Directory -Path "$output/owned" | Out-Null
$bin=Join-Path $output 'owned'
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE; $savedLib=$env:LIB
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $compiler=Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/ml64.exe') /nologo /c "/Fo$bin/Caller.obj" (Join-Path $PSScriptRoot 'Caller.asm')
    if($LASTEXITCODE -ne 0) { throw 'Owned gate caller assembly failed.' }
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 /LD (Join-Path $PSScriptRoot 'Consumer.cpp') "/Fo:$bin/Consumer.obj" "/Fe:$bin/GateConsumer.dll" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned gate consumer compilation failed.' }
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 (Join-Path $PSScriptRoot 'Target.cpp') "$bin/Caller.obj" "$bin/GateConsumer.lib" "/Fo:$bin/Target.obj" "/Fe:$bin/VmStartupControlTarget.exe" /link "/DEF:$PSScriptRoot/Target.def" /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned gate target compilation failed.' }
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 (Join-Path $PSScriptRoot 'Guardian.cpp') "/Fo:$bin/Guardian.obj" "/Fe:$bin/GateGuardian.exe" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned guardian compilation failed.' }
    $build=Join-Path $repo 'source/launch/startup_gate/Build.ps1'
    & $build -OutputDirectory "$output/owned-helper" -DetoursRoot $DetoursRoot -Python $Python -Fixture "$bin/VmStartupControlTarget.exe"
    & $build -OutputDirectory "$output/missing-helper" -DetoursRoot $DetoursRoot -Python $Python -Fixture "$bin/VmStartupControlTarget.exe" -MissingLoaderQuery
    & $build -OutputDirectory "$output/missing-anchor-helper" -DetoursRoot $DetoursRoot -Python $Python -Fixture "$bin/VmStartupControlTarget.exe" -MissingEntryAnchor
    & $build -OutputDirectory "$output/production" -DetoursRoot $DetoursRoot -Python $Python -CallerCapture $CallerCapture
    Copy-Item -LiteralPath "$output/owned-helper/Bo3StartupGate.dll" -Destination $bin
    New-Item -ItemType Directory -Path "$bin/missing-query" | Out-Null
    Copy-Item -LiteralPath "$output/missing-helper/Bo3StartupGate.dll" -Destination "$bin/missing-query"
    New-Item -ItemType Directory -Path "$bin/missing-anchor" | Out-Null
    Copy-Item -LiteralPath "$output/missing-anchor-helper/Bo3StartupGate.dll" -Destination "$bin/missing-anchor"
    $repoLiteral=$repo.Replace('\','\\')
    $header=@('#pragma once',"constexpr wchar_t kRepositoryRoot[]=L`"$repoLiteral`";")
    foreach($entry in @(@('Game','VmStartupControlTarget.exe'),@('Helper','Bo3StartupGate.dll'),@('Consumer','GateConsumer.dll'),@('Guardian','GateGuardian.exe'),@('MissingQuery','missing-query/Bo3StartupGate.dll'),@('MissingAnchor','missing-anchor/Bo3StartupGate.dll'))) {
        $header+="constexpr char k$($entry[0])Hash[]=`"$((Get-FileHash (Join-Path $bin $entry[1])).Hash.ToLowerInvariant())`";"
    }
    $rva=& $Python -c "import pefile; p=pefile.PE(r'$bin/Bo3StartupGate.dll'); print(next(e.address for e in p.DIRECTORY_ENTRY_EXPORT.symbols if e.name==b'Bo3StartupGateState'))"
    if($LASTEXITCODE -ne 0) { throw 'Cannot freeze owned gate export.' }
    $header+="constexpr unsigned int kStateRva=$($rva)u;"
    $header | Set-Content "$bin/BuildIdentity.h" -Encoding ascii
    $sources=@((Join-Path $PSScriptRoot 'Harness.cpp'),(Join-Path $repo 'source/launch/preentry/Identity.cpp'),(Join-Path $repo 'source/launch/enhanced/SteamContext.cpp'))
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 "/I$bin" "/I$DetoursRoot/include" @sources (Join-Path $DetoursRoot 'lib.X64/detours.lib') bcrypt.lib "/Fo:$bin/" "/Fe:$bin/GateHarness.exe" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned gate harness compilation failed.' }
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
$paths=@(Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName)+@("$bin/BuildIdentity.h",(Join-Path $repo 'source/launch/preentry/Identity.cpp'),(Join-Path $repo 'source/launch/preentry/Identity.h'),(Join-Path $repo 'source/launch/enhanced/SteamContext.cpp'),(Join-Path $repo 'source/launch/enhanced/SteamContext.h'),(Join-Path $repo 'source/launch/enhanced/PhysicalPath.ps1'),(Join-Path $repo 'source/launch/startup_gate/GateContract.h'),(Join-Path $repo 'source/launch/startup_probe/Observation.h'),(Join-Path $DetoursRoot 'include/detours.h'),(Join-Path $DetoursRoot 'lib.X64/detours.lib'))
@{scope='Fixed owned cooperative gate E2E. No game launch or native VM writes.'; sources=@($paths | Get-FileHash | Select-Object Path,Hash)} |
    ConvertTo-Json -Depth 5 | Set-Content "$output/native-build-receipt.json" -Encoding utf8
& $Python -B (Join-Path $PSScriptRoot 'Verify.py') --output $output
if($LASTEXITCODE -ne 0) { throw 'Owned gate E2E failed.' }
