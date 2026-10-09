#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$VmBuild,
    [Parameter(Mandatory)][string]$GateBuild,[Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../enhanced/PhysicalPath.ps1')
. (Join-Path $PSScriptRoot 'Compile.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private build directory.'}
$DetoursRoot=PhysicalPath $DetoursRoot
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no) -or
    (Get-FileHash $library).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC'){throw 'Use pinned unchanged Detours v4.0.1.'}
$vm=Get-Content (Join-Path $VmBuild 'build-receipt.json') -Raw | ConvertFrom-Json
$gate=Get-Content (Join-Path $GateBuild 'build-receipt.json') -Raw | ConvertFrom-Json
if($gate.fixture -or $gate.deadlineMs -ne 30000){throw 'The late launcher requires the fixed production gate build.'}
foreach($row in $gate.sources){if((Get-FileHash -LiteralPath $row.Path).Hash -ne $row.Hash){throw 'A gate build source differs from its receipt.'}}
if($vm.helperSha256 -ne '09b947ba384837853d5f4061a8fc3e2b61dee6b2663a751d6e7a2fb974c803c1' -or $gate.helperSha256 -ne 'd24f274e847c63015b24a513a202815b4e0ef6bd1078a9b73ae6aec1c71bd8ca'){throw 'Use the frozen production helper and gate.'}
$vmFile=Join-Path $VmBuild 'Bo3EnhancedHelper.dll';$gateFile=Join-Path $GateBuild 'Bo3StartupGate.dll'
if((Get-FileHash $vmFile).Hash.ToLowerInvariant() -ne $vm.helperSha256 -or (Get-FileHash $gateFile).Hash.ToLowerInvariant() -ne $gate.helperSha256){throw 'An exact helper differs from its build receipt.'}
New-Item -ItemType Directory -Path $output | Out-Null
Copy-Item -LiteralPath $vmFile,$gateFile -Destination $output
& $Python -B (Join-Path $repo 'source/launch/enhanced/Merge-Inventory.py') --vm (Join-Path $repo 'source/patches/vm_pool/exact_build_inventory.json') --migration (Join-Path $repo 'source/patches/vm_migration/exact_build_inventory.json') --output "$output/merged-inventory.json"
if($LASTEXITCODE -ne 0){throw 'Exact inventory merge failed.'}
& $Python -B (Join-Path $repo 'source/launch/enhanced/Generate-GameProfile.py') --inventory "$output/merged-inventory.json" --output "$output/GameManifest.h"
if($LASTEXITCODE -ne 0){throw 'Exact profile generation failed.'}
@('#pragma once','constexpr wchar_t kRepositoryRoot[]=L".";',
    'constexpr char kGameHash[]="0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0";',
    "constexpr char kHelperHash[]=`"$($vm.helperSha256)`";","constexpr char kGateHash[]=`"$($gate.helperSha256)`";") | Set-Content "$output/BuildIdentity.h" -Encoding ascii
& $Python -B (Join-Path $PSScriptRoot '../job_startup/Generate-WaitProfile.py') --gate "$output/Bo3StartupGate.dll" --output "$output/GateWaitProfile.h"
if($LASTEXITCODE -ne 0){throw 'Exact gate wait profile failed.'}
& $Python -B (Join-Path $PSScriptRoot '../job_startup/Generate-RuntimeProfile.py') --output "$output/RuntimeUnwindProfile.h"
if($LASTEXITCODE -ne 0){throw 'Exact runtime CRT profile failed.'}
$bootScript="import pefile;from pathlib import Path;import sys;p=pefile.PE(sys.argv[1]);r=next(e.address for e in p.DIRECTORY_ENTRY_EXPORT.symbols if e.name==b'Bo3EnhancedBoot');Path(sys.argv[2]).write_text('#pragma once\nconstexpr DWORD kHelperBootRva='+str(r)+'u;\n')"
& $Python -B -c $bootScript "$output/Bo3EnhancedHelper.dll" "$output/HelperBootProfile.h"
if($LASTEXITCODE -ne 0){throw 'Helper Boot profile failed.'}
$sources=Compile-BindingsControl -Repo $repo -Output $output -DetoursRoot $DetoursRoot
& $Python -B (Join-Path $PSScriptRoot 'Audit-Artifact.py') --directory $output --repository $repo
if($LASTEXITCODE -ne 0){throw 'Production job artifact audit failed.'}
Copy-Item -LiteralPath (Join-Path $DetoursRoot 'LICENSE.md') -Destination "$output/Detours-LICENSE.md"
$paths=@($sources)+@(Get-ChildItem $PSScriptRoot -File | Where-Object { $_.Extension -in @('.h','.cpp') -or $_.Name -in @('Build.ps1','Compile.ps1','README.txt','../job_startup/Generate-WaitProfile.py','Audit-Artifact.py') } | ForEach-Object FullName)+@("$output/GameManifest.h","$output/BuildIdentity.h","$output/GateWaitProfile.h","$output/GateWaitProfile.json","$output/artifact-audit.json","$output/merged-inventory.json",$vmFile,$gateFile,(Join-Path $GateBuild 'build-receipt.json'),$library)
$paths+=@('vm_pool','vm_startup','vm_migration') | ForEach-Object {Get-ChildItem (Join-Path $repo "source/patches/$_") -File | Where-Object Extension -in @('.h','.json') | ForEach-Object FullName}
$paths+=@('GameProfile.h','MappedHelper.h','SteamContext.h','Boot.h','LaunchLease.h') | ForEach-Object {Join-Path $repo "source/launch/enhanced/$_"}
$paths+=Join-Path $repo 'source/launch/job_control/Originals.h'
$paths+=Get-ChildItem (Join-Path $repo 'source/launch/process_freeze') -File | Where-Object Extension -in @('.h','.cpp') | ForEach-Object FullName
$paths+=Get-ChildItem (Join-Path $repo 'source/launch/late_startup') -File | Where-Object Extension -in @('.h','.cpp') | ForEach-Object FullName
$paths+=Get-ChildItem (Join-Path $repo 'source/launch/job_startup') -File | Where-Object {$_.Extension -in @('.h','.cpp','.py','.json') -and $_.Name -notlike 'Steam*'} | ForEach-Object FullName
$paths+=@(Join-Path $repo 'source/launch/preentry/Identity.h';Join-Path $repo 'source/launch/startup_gate/GateContract.h')
$paths+=@((Join-Path $PSScriptRoot '../job_startup/RuntimeUnwind.json'),(Join-Path $PSScriptRoot '../job_startup/Generate-RuntimeProfile.py'),"$output/RuntimeUnwindProfile.h","$output/HelperBootProfile.h")
@{scope='Bounded bindings-only diagnostic. Seven helper records plus two relay blocks; all 33 game spans remain stock. No game launch or hook activation.';startupMethod='late-crt-job-freeze-bindings-control';serverTotal=130000;clientRoots=8;intendedUnpublishedServerTotal=500001;committed=$false;plannedPublications=9;gameInstructionEdits=0;observationLimitMs=120000;deadlineMs=30000;
    launcherSha256=(Get-FileHash "$output/BO3-Bindings-Control.exe").Hash;helperSha256=$vm.helperSha256;gateSha256=$gate.helperSha256;
    files=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 6 | Set-Content "$output/build-receipt.json" -Encoding utf8
