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
$sources=Compile-LateStartup -Repo $repo -Output $output -DetoursRoot $DetoursRoot
Copy-Item -LiteralPath (Join-Path $DetoursRoot 'LICENSE.md') -Destination "$output/Detours-LICENSE.md"
$paths=@($sources)+@(Get-ChildItem $PSScriptRoot -File | Where-Object { $_.Extension -in @('.h','.cpp') -or $_.Name -in @('Build.ps1','Compile.ps1','README.txt') } | ForEach-Object FullName)+@("$output/GameManifest.h","$output/BuildIdentity.h","$output/merged-inventory.json",$vmFile,$gateFile,(Join-Path $GateBuild 'build-receipt.json'),$library)
$paths+=@('vm_pool','vm_startup','vm_migration') | ForEach-Object {Get-ChildItem (Join-Path $repo "source/patches/$_") -File | Where-Object Extension -in @('.h','.json') | ForEach-Object FullName}
$paths+=@('GameProfile.h','MappedHelper.h','SteamContext.h','Boot.h','LaunchLease.h') | ForEach-Object {Join-Path $repo "source/launch/enhanced/$_"}
$paths+=@(Join-Path $repo 'source/launch/preentry/Identity.h';Join-Path $repo 'source/launch/startup_gate/GateContract.h')
@{scope='Experimental exact late CRT gate candidate. No launch or activation validation.';serverTotal=500001;clientRoots=18;migrationBufferBytes=33554432;deadlineMs=30000;
    launcherSha256=(Get-FileHash "$output/BO3-Late-Zombies.exe").Hash;helperSha256=$vm.helperSha256;gateSha256=$gate.helperSha256;
    files=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 6 | Set-Content "$output/build-receipt.json" -Encoding utf8
