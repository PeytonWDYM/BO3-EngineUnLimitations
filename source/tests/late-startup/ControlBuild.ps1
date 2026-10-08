#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$VmBuild,
    [Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python,[Parameter(Mandatory)][string]$Dependencies,
    [Parameter(Mandatory)][string]$StartupDump)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
. (Join-Path $PSScriptRoot '../../launch/late_startup/CompileControl.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private owned output.'}
New-Item -ItemType Directory -Path $output | Out-Null
& $Python -B (Join-Path $repo 'source/launch/enhanced/Merge-Inventory.py') --vm (Join-Path $repo 'source/patches/vm_pool/exact_build_inventory.json') --migration (Join-Path $repo 'source/patches/vm_migration/exact_build_inventory.json') --output "$output/merged-inventory.json"
if($LASTEXITCODE -ne 0){throw 'Owned inventory merge failed.'}
& $Python -B (Join-Path $repo 'source/launch/enhanced/Generate-GameProfile.py') --inventory "$output/merged-inventory.json" --output "$output/GameManifest.h"
if($LASTEXITCODE -ne 0){throw 'Owned fixed profile failed.'}
& $Python -B (Join-Path $PSScriptRoot 'Seed.py') --dump $StartupDump --inventory "$output/merged-inventory.json" --dependencies $Dependencies --output "$output/seed.bin" --control
if($LASTEXITCODE -ne 0){throw 'Owned startup seed identity failed.'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE;$savedLib=$env:LIB
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/ml64.exe') /nologo /c "/Fo$output/Caller.obj" (Join-Path $repo 'source/tests/startup-probe/Caller.asm')
    if($LASTEXITCODE -ne 0){throw 'Owned late caller assembly failed.'}
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 /DBO3_LATE_STOCK_CONTROL_TARGET "/I$output" "/I$repo/source/launch/enhanced" (Join-Path $PSScriptRoot 'Target.cpp') "$output/Caller.obj" "/Fo:$output/Target.obj" "/Fe:$output/VmStartupControlTarget.exe" /link "/DEF:$PSScriptRoot/Target.def" /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned late target compilation failed.'}
}finally{$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
& (Join-Path $repo 'source/launch/startup_gate/Build.ps1') -OutputDirectory "$output/gate-build" -DetoursRoot $DetoursRoot -Python $Python -Fixture "$output/VmStartupControlTarget.exe"
if($LASTEXITCODE -ne 0){throw 'Owned exact gate build failed.'}
$vm=Get-Content (Join-Path $VmBuild 'build-receipt.json') -Raw | ConvertFrom-Json
$vmFile=Join-Path $VmBuild 'Bo3EnhancedHelper.dll'
if((Get-FileHash $vmFile).Hash.ToLowerInvariant() -ne $vm.helperSha256){throw 'The combined VM helper differs.'}
Copy-Item -LiteralPath $vmFile,"$output/gate-build/Bo3StartupGate.dll" -Destination $output
@('#pragma once',"constexpr wchar_t kRepositoryRoot[]=L`"$($repo.Replace('\','\\'))`";",
    "constexpr char kOwnedTargetHash[]=`"$((Get-FileHash "$output/VmStartupControlTarget.exe").Hash.ToLowerInvariant())`";",
    "constexpr char kHelperHash[]=`"$($vm.helperSha256)`";","constexpr char kGateHash[]=`"$((Get-FileHash "$output/Bo3StartupGate.dll").Hash.ToLowerInvariant())`";",
    "constexpr char kSeedHash[]=`"$((Get-FileHash "$output/seed.bin").Hash.ToLowerInvariant())`";") | Set-Content "$output/BuildIdentity.h" -Encoding ascii
$exportScript="import sys;sys.path.insert(0,sys.argv[1]);import pefile;from pathlib import Path;`ntext='#pragma once\n';`nfor file,name,symbol in [(sys.argv[2],'OwnedImage','OwnedImage'),(sys.argv[2],'TriggerBreak','TriggerBreak'),(sys.argv[3],'GateState','Bo3StartupGateState')]:`n p=pefile.PE(file);rva=next(e.address for e in p.DIRECTORY_ENTRY_EXPORT.symbols if e.name==symbol.encode());text+=f'constexpr DWORD k{name}Rva={rva}u;\n'`nPath(sys.argv[4]).write_text(text)"
$exportScript | Set-Content "$output/Export-Offsets.py" -Encoding utf8
& $Python -B "$output/Export-Offsets.py" $Dependencies "$output/VmStartupControlTarget.exe" "$output/Bo3StartupGate.dll" "$output/TargetExports.h"
if($LASTEXITCODE -ne 0){throw 'Owned export extraction failed.'}
$sources=Compile-LateControl -Repo $repo -Output $output -DetoursRoot $DetoursRoot -Owned
$cases=@()
foreach($case in @('success','guard','allocated','call','target','continue','detach','early-exit','timeout','pre-gate-exit')) {
    & "$output/LateControlOwnedFixture.exe" $case "$output/$case.json"
    if($LASTEXITCODE -ne 0){throw "Owned late gate case failed: $case"}
    $cases+=Get-Content "$output/$case.json" -Raw | ConvertFrom-Json
}
$paths=@($sources)+@(Get-ChildItem $PSScriptRoot -File | Where-Object { $_.Name -notlike 'Steam*' } | ForEach-Object FullName)+@(Get-ChildItem (Join-Path $repo 'source/launch/late_startup') -File | Where-Object { $_.Extension -in @('.h','.cpp') -or $_.Name -in @('Build.ps1','Compile.ps1','README.txt') } | ForEach-Object FullName)+@("$output/GameManifest.h","$output/BuildIdentity.h","$output/TargetExports.h","$output/seed.bin",(Join-Path $repo 'source/launch/startup_gate/GateContract.h'))
$paths+=@('vm_pool','vm_startup','vm_migration') | ForEach-Object {Get-ChildItem (Join-Path $repo "source/patches/$_") -File | Where-Object Extension -in @('.h','.json') | ForEach-Object FullName}
$paths+=@('GameProfile.h','MappedHelper.h','SteamContext.h','Boot.h') | ForEach-Object {Join-Path $repo "source/launch/enhanced/$_"}
$paths+=Join-Path $repo 'source/launch/preentry/Identity.h'
@{passed=$true;scope='Owned stock-capacity late attachment with zero native edits and no relay plan. No BO3 execution.';
    cases=$cases;os=Get-ComputerInfo -Property OsName,OsVersion,OsBuildNumber;
    files=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash);
    artifacts=@(Get-ChildItem $output -File | Where-Object Extension -in @('.bin','.json','.exe','.dll') | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 8 | Set-Content "$output/result.json" -Encoding utf8
