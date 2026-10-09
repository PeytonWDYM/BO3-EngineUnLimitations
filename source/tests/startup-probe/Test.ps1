#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$DetoursRoot,
    [Parameter(Mandatory)][string]$Python,[Parameter(Mandatory)][string]$CallerCapture)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..'); $output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep probe E2E outside the repository.' }
if(Test-Path -LiteralPath $output) { throw 'Use a new probe E2E directory.' }
New-Item -ItemType Directory -Path "$output/fixture" | Out-Null
$fixture=Join-Path $output 'fixture'
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
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/ml64.exe') /nologo /c "/Fo$fixture/Caller.obj" (Join-Path $PSScriptRoot 'Caller.asm')
    if($LASTEXITCODE -ne 0) { throw 'Owned caller assembly failed.' }
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 /LD (Join-Path $PSScriptRoot 'Consumer.cpp') "/Fo:$fixture/Consumer.obj" "/Fe:$fixture/ProbeConsumer.dll" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned consumer compilation failed.' }
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 (Join-Path $PSScriptRoot 'Target.cpp') "$fixture/Caller.obj" "$fixture/ProbeConsumer.lib" "/Fo:$fixture/Target.obj" "/Fe:$fixture/VmStartupControlTarget.exe" /link "/DEF:$PSScriptRoot/Target.def" /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned probe target compilation failed.' }
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
$build=Join-Path $repo 'source/launch/startup_probe/Build.ps1'
$controllerBuild=Join-Path $repo 'source/launch/enhanced/Build-StartupDiagnostic.ps1'
$target=Join-Path $fixture 'VmStartupControlTarget.exe'
foreach($kind in @('production','owned','boot-failure')) {
    $helper=Join-Path $output "$kind-helper"
    if($kind -eq 'production') {
        & $build -OutputDirectory $helper -DetoursRoot $DetoursRoot -Python $Python -CallerCapture $CallerCapture
    } else {
        & $build -OutputDirectory $helper -DetoursRoot $DetoursRoot -Python $Python -Fixture $target -RefuseFixtureIdentity:($kind -eq 'boot-failure')
    }
    if($LASTEXITCODE -ne 0) { throw 'Probe helper build failed.' }
    $bin=Join-Path $output $kind
    & $controllerBuild -OutputDirectory $bin -ProductionBuild $helper -DetoursRoot $DetoursRoot -Python $Python
    if($LASTEXITCODE -ne 0) { throw 'Probe controller build failed.' }
    if($kind -ne 'production') {
        Copy-Item -LiteralPath $target,(Join-Path $fixture 'ProbeConsumer.dll') -Destination $bin
        $repoLiteral=$repo.Replace('\','\\')
        @('#pragma once',"constexpr wchar_t kRepositoryRoot[]=L`"$repoLiteral`";", "constexpr char kGameHash[]=`"$((Get-FileHash $target).Hash.ToLowerInvariant())`";",
            "constexpr char kHelperHash[]=`"$((Get-FileHash (Join-Path $bin 'Bo3EnhancedHelper.dll')).Hash.ToLowerInvariant())`";") | Set-Content (Join-Path $bin 'BuildIdentity.h') -Encoding ascii
        & $Python -B (Join-Path $repo 'source/tests/vm-startup/Control-Profile.py') --helper (Join-Path $bin 'Bo3EnhancedHelper.dll') --fixture (Join-Path $bin 'VmStartupControlTarget.exe') --output (Join-Path $bin 'ControlProfile.h')
        if($LASTEXITCODE -ne 0) { throw 'Owned controller profile generation failed.' }
        & (Join-Path $repo 'source/tests/vm-startup/Compile-StartupControl.ps1') -OutputDirectory $bin -DetoursRoot $DetoursRoot
        if($LASTEXITCODE -ne 0) { throw 'Owned controller compile failed.' }
        $receiptFile=Join-Path $bin 'diagnostic-build-receipt.json'
        $prior=Get-Content -LiteralPath $receiptFile -Raw | ConvertFrom-Json
        $inputs=@($prior.files.Path)+@($target,(Join-Path $bin 'ProbeConsumer.dll'))+@(Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName)
        @{scope='Owned fixed-profile startup API probe controller. No stock game launch.';
            detoursCommit=$prior.detoursCommit; files=@($inputs | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash)} |
            ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receiptFile -Encoding utf8
    }
}
& $Python -B (Join-Path $PSScriptRoot 'Verify.py') --output $output
if($LASTEXITCODE -ne 0) { throw 'Native startup probe E2E failed.' }
