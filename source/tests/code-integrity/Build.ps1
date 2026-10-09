#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$output=[IO.Path]::GetFullPath($OutputDirectory)
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private proof directory.'}
New-Item -ItemType Directory -Path $output | Out-Null
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
    $flags=@('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2','/DBO3_CODE_INTEGRITY_OWNED_TEST',"/I$output","/I$repo/source/patches/code_integrity")
    & $cl @flags /LD (Join-Path $PSScriptRoot 'Image.cpp') "/Fo$output/Image.obj" "/Fe$output/IntegrityOwnedImage.dll" /link /SECTION:.owned,ERW /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned image compilation failed.'}
    & $Python -B (Join-Path $PSScriptRoot 'Generate-Fixture.py') "$output/IntegrityOwnedImage.dll" "$output/Profile.h"
    if($LASTEXITCODE -ne 0){throw 'Owned profile generation failed.'}
    & $cl @flags (Join-Path $PSScriptRoot 'Target.cpp') "/Fo$output/Target.obj" "/Fe$output/IntegrityOwnedTarget.exe" /link /SUBSYSTEM:WINDOWS /ENTRY:wmainCRTStartup /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned child compilation failed.'}
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/ml64.exe') /nologo /c "/Fo$output/Evaluator.obj" (Join-Path $PSScriptRoot 'Evaluator.asm')
    if($LASTEXITCODE -ne 0){throw 'Authored snippet assembly failed.'}
    $sources=@('Runner.cpp','Semantics.cpp') | ForEach-Object {Join-Path $PSScriptRoot $_}
    $sources+=Join-Path $repo 'source/patches/code_integrity/Plan.cpp'
    $sources+=Join-Path $repo 'source/patches/vm_startup/PausedPatch.cpp'
    $sources+=@('NativeJobFreeze.cpp','NativeState.cpp') | ForEach-Object {Join-Path $repo "source/launch/process_freeze/$_"}
    & $cl @flags @sources "$output/Evaluator.obj" "/Fo$output/" "/Fe$output/IntegrityOwnedProof.exe" /link bcrypt.lib /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned proof compilation failed.'}
    $cases=@()
    foreach($case in @('success','identity','guard','original','context','pointer','timestamp','machine','size','protection','private','overflow','overlap','rollback','rollbackfailed')) {
        & "$output/IntegrityOwnedProof.exe" $case "$output/$case.json"
        if($LASTEXITCODE -ne 0){throw "Owned proof case failed: $case"}
        $cases+=Get-Content -LiteralPath "$output/$case.json" -Raw | ConvertFrom-Json
    }
    $production=Join-Path $output 'production-refusal'
    New-Item -ItemType Directory -Path $production | Out-Null
    $productionFlags=$flags | Where-Object {$_ -ne '/DBO3_CODE_INTEGRITY_OWNED_TEST'}
    & $cl @productionFlags @sources "$output/Evaluator.obj" "/Fo$production/" "/Fe$output/IntegrityProductionRefusalProof.exe" /link bcrypt.lib /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Production-refusal proof compilation failed.'}
    & "$output/IntegrityProductionRefusalProof.exe" production "$output/production.json"
    if($LASTEXITCODE -ne 0){throw 'Production preparation did not refuse.'}
    $cases+=Get-Content -LiteralPath "$output/production.json" -Raw | ConvertFrom-Json
    $paths=@($sources)+@(Get-ChildItem -LiteralPath $PSScriptRoot -File | ForEach-Object FullName)
    $paths+=Get-ChildItem -LiteralPath (Join-Path $repo 'source/patches/code_integrity') -File | ForEach-Object FullName
    $paths+=@("$output/Profile.h",'C:\Windows\System32\ntdll.dll')
    @{passed=$true;scope='Authored inert MEM_IMAGE fixture in an owned frozen job. No game or Steam execution.';cases=$cases;sources=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash);artifacts=@(Get-ChildItem -LiteralPath $output -File | Where-Object Extension -in @('.exe','.dll','.json','.h','.bin') | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$output/result.json" -Encoding utf8
}finally{$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
