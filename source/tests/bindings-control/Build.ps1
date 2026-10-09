#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$FrozenOwnedBuild,
    [Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
. (Join-Path $PSScriptRoot '../../launch/bindings_control/Compile.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private owned output.'}
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no) -or
    (Get-FileHash $library).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC'){throw 'Use pinned unchanged Detours.'}
$prior=Get-Content (Join-Path $FrozenOwnedBuild 'result.json') -Raw | ConvertFrom-Json
if(!$prior.passed){throw 'The inert captured seed requires its passing frozen receipt.'}
foreach($name in @('seed.bin','GameManifest.h','merged-inventory.json','Bo3EnhancedHelper.dll')) {
    $file=Join-Path $FrozenOwnedBuild $name
    $row=@($prior.artifacts)+@($prior.files) | Where-Object {$_.Path -eq $file} | Select-Object -First 1
    if(!$row -or (Get-FileHash $file).Hash -ne $row.Hash){throw "The frozen inert fixture file differs: $name"}
}
New-Item -ItemType Directory -Path $output | Out-Null
foreach($name in @('seed.bin','GameManifest.h','merged-inventory.json','Bo3EnhancedHelper.dll')){Copy-Item -LiteralPath (Join-Path $FrozenOwnedBuild $name) -Destination $output}
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
    if($LASTEXITCODE -ne 0){throw 'Owned job caller assembly failed.'}
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 "/I$output" "/I$repo/source/launch/enhanced" (Join-Path $PSScriptRoot 'Target.cpp') "$output/Caller.obj" "/Fo:$output/Target.obj" "/Fe:$output/VmStartupControlTarget.exe" /link /SUBSYSTEM:WINDOWS /ENTRY:wmainCRTStartup "/DEF:$repo/source/tests/late-startup/Target.def" /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned job target compilation failed.'}
}finally{$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
& $Python -B (Join-Path $repo 'source/launch/job_startup/Generate-RuntimeProfile.py') --fixture "$output/VmStartupControlTarget.exe" --output "$output/RuntimeUnwindProfile.h"
if($LASTEXITCODE -ne 0){throw 'Owned runtime CRT profile failed.'}
& $Python -B (Join-Path $PSScriptRoot '../job-startup/Encrypt-Unwind.py') "$output/VmStartupControlTarget.exe" "$output/encrypted-unwind.json"
if($LASTEXITCODE -ne 0){throw 'Owned encrypted unwind preparation failed.'}
& (Join-Path $repo 'source/launch/startup_gate/Build.ps1') -OutputDirectory "$output/gate-build" -DetoursRoot $DetoursRoot -Python $Python -Fixture "$output/VmStartupControlTarget.exe"
if($LASTEXITCODE -ne 0){throw 'Owned exact job gate build failed.'}
# The frozen child cannot run its gate timeout. Match the production parent's absolute budget.
$profile=Get-Content "$output/gate-build/GateProfile.h" -Raw
$profile.Replace('1000u','30000u') | Set-Content "$output/gate-build/GateProfile.h" -Encoding ascii
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $gateSources=@('Helper','Admission','Gate','NativeEntry') | ForEach-Object {Join-Path $repo "source/launch/startup_gate/$_.cpp"}
    $gateSources+=Join-Path $repo 'source/launch/startup_probe/Observation.cpp'
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 /LD "/I$output/gate-build" "/I$DetoursRoot/include" @gateSources $library OneCore.lib "/Fo:$output/gate-build/" "/Fe:$output/gate-build/Bo3StartupGate.dll" /link "/DEF:$repo/source/launch/startup_gate/Helper.def" /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned 30-second gate compilation failed.'}
}finally{$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
$gateReceipt=Get-Content "$output/gate-build/build-receipt.json" -Raw | ConvertFrom-Json
$gateReceipt.helperSha256=(Get-FileHash "$output/gate-build/Bo3StartupGate.dll").Hash.ToLowerInvariant()
$gateReceipt.deadlineMs=30000
$gateReceipt.scope='Owned serial-loader fixture gate. Same source contract with the production 30-second deadline.'
foreach($row in $gateReceipt.sources){$row.Hash=(Get-FileHash -LiteralPath $row.Path).Hash}
$gateReceipt | ConvertTo-Json -Depth 6 | Set-Content "$output/gate-build/build-receipt.json" -Encoding utf8
Copy-Item -LiteralPath "$output/gate-build/Bo3StartupGate.dll" -Destination $output
@('#pragma once',"constexpr wchar_t kRepositoryRoot[]=L`"$($repo.Replace('\','\\'))`";",
    "constexpr char kOwnedTargetHash[]=`"$((Get-FileHash "$output/VmStartupControlTarget.exe").Hash.ToLowerInvariant())`";",
    "constexpr char kGameHash[]=`"$((Get-FileHash "$output/VmStartupControlTarget.exe").Hash.ToLowerInvariant())`";",
    "constexpr char kHelperHash[]=`"$((Get-FileHash "$output/Bo3EnhancedHelper.dll").Hash.ToLowerInvariant())`";",
    "constexpr char kGateHash[]=`"$((Get-FileHash "$output/Bo3StartupGate.dll").Hash.ToLowerInvariant())`";",
    "constexpr char kSeedHash[]=`"$((Get-FileHash "$output/seed.bin").Hash.ToLowerInvariant())`";") | Set-Content "$output/BuildIdentity.h" -Encoding ascii
& $Python -B (Join-Path $repo 'source/launch/job_startup/Generate-WaitProfile.py') --gate "$output/Bo3StartupGate.dll" --output "$output/GateWaitProfile.h"
if($LASTEXITCODE -ne 0){throw 'Owned gate wait profile failed.'}
$script="import pefile;from pathlib import Path;import sys;p=pefile.PE(sys.argv[1]);e={x.name.decode():x.address for x in p.DIRECTORY_ENTRY_EXPORT.symbols if x.name};Path(sys.argv[2]).write_text('#pragma once\nconstexpr DWORD kOwnedImageRva='+str(e['OwnedImage'])+'u;\n')"
& $Python -B -c $script "$output/VmStartupControlTarget.exe" "$output/TargetExports.h"
if($LASTEXITCODE -ne 0){throw 'Owned image export failed.'}
$bootScript="import pefile;from pathlib import Path;import sys;p=pefile.PE(sys.argv[1]);r=next(e.address for e in p.DIRECTORY_ENTRY_EXPORT.symbols if e.name==b'Bo3EnhancedBoot');Path(sys.argv[2]).write_text('#pragma once\nconstexpr DWORD kHelperBootRva='+str(r)+'u;\n')"
& $Python -B -c $bootScript "$output/Bo3EnhancedHelper.dll" "$output/HelperBootProfile.h"
if($LASTEXITCODE -ne 0){throw 'Helper Boot profile failed.'}
$sources=Compile-BindingsControl -Repo $repo -Output $output -DetoursRoot $DetoursRoot -Owned
& $Python -B (Join-Path $repo 'source/launch/bindings_control/Audit-Artifact.py') --directory $output --owned --repository $repo
if($LASTEXITCODE -ne 0){throw 'Owned job artifact audit failed.'}
$cases=@()
foreach($case in @('success','guard','allocated','helper','extra-thread','membership','rollback','rollback-failed','deadline','thaw','release','early-exit','parent-death')) {
    & "$output/BindingsControlOwnedFixture.exe" $case "$output/$case.json"
    if($LASTEXITCODE -ne 0){throw "Owned job case failed: $case"}
    $cases+=Get-Content "$output/$case.json" -Raw | ConvertFrom-Json
}
& $Python -B (Join-Path $PSScriptRoot 'Verify-Evidence.py') $output
if($LASTEXITCODE -ne 0){throw 'Owned stock evidence verification failed.'}
$paths=@($sources)+@(Get-ChildItem $PSScriptRoot -File | Where-Object { $_.Name -notlike 'Steam*' } | ForEach-Object FullName)
$paths+=@(Get-ChildItem (Join-Path $repo 'source/launch/bindings_control') -File | Where-Object {$_.Name -notlike 'Steam*'} | ForEach-Object FullName)
$paths+=@(Get-ChildItem (Join-Path $repo 'source/launch/job_startup') -File | Where-Object {$_.Name -notlike 'Steam*'} | ForEach-Object FullName)
$paths+=@(Join-Path $repo 'source/launch/job_control/Originals.h';Join-Path $repo 'source/tests/job-startup/ParentDeath.h')
$paths+=@('vm_pool','vm_startup','vm_migration') | ForEach-Object {Get-ChildItem (Join-Path $repo "source/patches/$_") -File | Where-Object Extension -in @('.h','.json') | ForEach-Object FullName}
$paths+=Get-ChildItem (Join-Path $repo 'source/launch/enhanced') -File -Filter '*.h' | ForEach-Object FullName
$paths+=@('C:\Windows\System32\ntdll.dll','C:\Windows\System32\kernel32.dll','C:\Windows\System32\KernelBase.dll')
$paths+=@('source/tests/job-startup/SerialLoader.h','source/tests/job-startup/Encrypt-Unwind.py','source/launch/late_startup/ControlAdmission.h','source/launch/late_startup/PrivateReceipt.h') | ForEach-Object {Join-Path $repo $_}
$paths+=@($gateSources)+@(Get-ChildItem "$output/gate-build" -File | Where-Object Extension -in @('.h','.json') | ForEach-Object FullName)
$paths+=@("$output/GameManifest.h","$output/BuildIdentity.h","$output/GateWaitProfile.h","$output/RuntimeUnwindProfile.h","$output/HelperBootProfile.h","$output/TargetExports.h","$output/seed.bin",$library)
$paths+=@('source/tests/startup-probe/Caller.asm','source/tests/late-startup/Target.def','source/launch/startup_gate/Build.ps1','source/launch/startup_probe/Generate-Profile.py','source/patches/vm_startup/PausedPatch.h','source/launch/late_startup/OwnedChild.h','source/launch/late_startup/MappedGate.h','source/launch/late_startup/FixedPlan.h','source/launch/late_startup/PrivateReceipt.h','source/launch/late_startup/Coordinator.h','source/launch/startup_gate/GateContract.h','source/launch/process_freeze/NativeJobFreeze.h','source/launch/process_freeze/NativeState.h') | ForEach-Object {Join-Path $repo $_}
@{passed=$true;scope='Owned inert image; same job/full-unwind stock admission. Exactly nine helper/relay publications, 33 withheld stock instructions. Parent seed under freeze, serialized loader fixture only. No game execution.';cases=$cases;
    files=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash);
    artifacts=@(Get-ChildItem $output -File | Where-Object Extension -in @('.bin','.json','.exe','.dll') | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 8 | Set-Content "$output/result.json" -Encoding utf8
