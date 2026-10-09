#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$output=[IO.Path]::GetFullPath($OutputDirectory)
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private proof directory.'}
if(-not (Test-Path -LiteralPath $Python -PathType Leaf)){throw 'The supplied Python does not exist.'}
New-Item -ItemType Directory -Path $output | Out-Null
$evidence='C:/Users/plamb/.codex/labs/bo3-engine/evidence/release-enhancement'
& uv pip install --python $Python --target "$output/python" unicorn==2.1.4
if($LASTEXITCODE -ne 0){throw 'Private instruction emulator setup failed.'}
& $Python -B (Join-Path $PSScriptRoot 'Audit.py') --evidence $evidence --output $output --unicorn "$output/python"
if($LASTEXITCODE -ne 0){throw 'Independent exact-flow admission failed.'}
$public=Join-Path $repo 'source/patches/early_integrity/exact_build_profile.json'
if((Get-FileHash -LiteralPath "$output/exact_build_profile.json").Hash -ne (Get-FileHash -LiteralPath $public).Hash){throw 'Independent profile differs from the public profile.'}
& $Python -B (Join-Path $repo 'source/patches/early_integrity/Generate-Profile.py') --output "$output/EarlyIntegrityProfile.h"
if($LASTEXITCODE -ne 0){throw 'Fixed profile generation failed.'}
& $Python -B (Join-Path $PSScriptRoot 'Create-Fixture.py') --profile $public --guards "$output/private-guards.json" --captured-image "$evidence/integrity-input-audit-sol-03/runtime-image.bin" --output "$output/EarlyIntegrityOwnedImage.dll"
if($LASTEXITCODE -ne 0){throw 'Private inert image generation failed.'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE;$savedLib=$env:LIB
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $cl=Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    $flags=@('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2',"/I$output","/I$repo/source/patches/early_integrity")
    & $cl @flags (Join-Path $PSScriptRoot 'Target.cpp') "/Fo$output/Target.obj" "/Fe$output/EarlyIntegrityOwnedTarget.exe" /link /SUBSYSTEM:WINDOWS /ENTRY:wmainCRTStartup /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned target compilation failed.'}
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/ml64.exe') /nologo /c "/Fo$output/Probe.obj" (Join-Path $PSScriptRoot 'Probe.asm')
    if($LASTEXITCODE -ne 0){throw 'Authored probe assembly failed.'}
    $sources=@('Runner.cpp','Semantics.cpp') | ForEach-Object {Join-Path $PSScriptRoot $_}
    $sources+=Join-Path $repo 'source/patches/early_integrity/Plan.cpp'
    $sources+=Join-Path $repo 'source/patches/vm_startup/PausedPatch.cpp'
    $sources+=@('NativeJobFreeze.cpp','NativeState.cpp') | ForEach-Object {Join-Path $repo "source/launch/process_freeze/$_"}
    & $cl @flags @sources "$output/Probe.obj" "/Fo$output/" "/Fe$output/EarlyIntegrityOwnedProof.exe" /link bcrypt.lib /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned proof compilation failed.'}
    $cases=@()
    foreach($case in @('semantics','success','expected','identity','source','store','context','pointer','scan','overlap','expectedoverlap','chainoverlap','machine','timestamp','size','protection','private','overflow','rollback')) {
        & "$output/EarlyIntegrityOwnedProof.exe" $case "$output/$case.json"
        if($LASTEXITCODE -ne 0){throw "Owned case failed: $case"}
        $cases+=Get-Content -LiteralPath "$output/$case.json" -Raw | ConvertFrom-Json
    }
    $paths=@($sources)+@(Get-ChildItem -LiteralPath $PSScriptRoot -File | ForEach-Object FullName)
    $paths+=Get-ChildItem -LiteralPath (Join-Path $repo 'source/patches/early_integrity') -File | ForEach-Object FullName
    $paths+=@("$output/EarlyIntegrityProfile.h",'C:/Windows/System32/ntdll.dll')
    @{passed=$true;scope='Owned inert MEM_IMAGE admission, authored native relays and saved-code emulator replay. No game execution.';cases=$cases;flowProof=Get-Content -LiteralPath "$output/flow-proof.json" -Raw | ConvertFrom-Json;sources=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash);artifacts=@(Get-ChildItem -LiteralPath $output -File | Where-Object Extension -in @('.exe','.dll','.json','.h') | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$output/result.json" -Encoding utf8
}finally{$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
