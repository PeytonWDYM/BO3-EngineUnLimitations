#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$FrozenNative,
    [Parameter(Mandatory)][string]$DetoursRoot)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../enhanced/PhysicalPath.ps1')
. (Join-Path $PSScriptRoot 'CompileControl.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private control build directory.'}
$DetoursRoot=PhysicalPath $DetoursRoot
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no) -or
    (Get-FileHash $library).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC'){throw 'Use pinned unchanged Detours v4.0.1.'}
$pins=@{'Bo3EnhancedHelper.dll'='09b947ba384837853d5f4061a8fc3e2b61dee6b2663a751d6e7a2fb974c803c1';
    'Bo3StartupGate.dll'='d24f274e847c63015b24a513a202815b4e0ef6bd1078a9b73ae6aec1c71bd8ca'}
foreach($name in $pins.Keys){if((Get-FileHash (Join-Path $FrozenNative $name)).Hash.ToLowerInvariant() -ne $pins[$name]){throw 'A frozen control helper differs.'}}
New-Item -ItemType Directory -Path $output | Out-Null
foreach($name in $pins.Keys){Copy-Item -LiteralPath (Join-Path $FrozenNative $name) -Destination $output}
$manifest=Join-Path (Split-Path $FrozenNative -Parent) '../production-01/GameManifest.h'
# The manifest belongs to the same complete, admitted inventory as the frozen candidate.
Copy-Item -LiteralPath $manifest -Destination "$output/GameManifest.h"
if((Get-FileHash "$output/GameManifest.h").Hash -ne '827AEF4DD3AEA588D2718765AC61D17EB1F1C31A8A43CAD4998F71C30C509982'){throw 'The complete fixed manifest differs.'}
@('#pragma once','constexpr wchar_t kRepositoryRoot[]=L".";',
    'constexpr char kGameHash[]="0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0";',
    "constexpr char kHelperHash[]=`"$($pins['Bo3EnhancedHelper.dll'])`";", "constexpr char kGateHash[]=`"$($pins['Bo3StartupGate.dll'])`";") | Set-Content "$output/BuildIdentity.h" -Encoding ascii
$sources=Compile-LateControl -Repo $repo -Output $output -DetoursRoot $DetoursRoot
Copy-Item -LiteralPath (Join-Path $DetoursRoot 'LICENSE.md') -Destination "$output/Detours-LICENSE.md"
$paths=@($sources)+@("$output/GameManifest.h","$output/BuildIdentity.h",$library)+@(Get-ChildItem $PSScriptRoot -File | Where-Object { $_.Name -in @('Coordinator.h','ControlAdmission.h','ControlAdmission.cpp','ControlLauncher.cpp','BuildControl.ps1','CompileControl.ps1','PrivateReceipt.h','PrivateReceipt.cpp','OwnedChild.h','MappedGate.h') } | ForEach-Object FullName)
$paths+=Join-Path $repo 'source/tests/late-startup/ControlFailures.txt'
$paths+=@('vm_pool','vm_startup','vm_migration') | ForEach-Object {Get-ChildItem (Join-Path $repo "source/patches/$_") -File | Where-Object Extension -in @('.h','.json') | ForEach-Object FullName}
$paths+=@('GameProfile.h','MappedHelper.h','SteamContext.h','Boot.h','LaunchLease.h','PhysicalPath.ps1') | ForEach-Object {Join-Path $repo "source/launch/enhanced/$_"}
$paths+=@(Join-Path $repo 'source/launch/preentry/Identity.h';Join-Path $repo 'source/launch/startup_gate/GateContract.h')
@{scope='Fixed stock-capacity late CRT control. No BO3 launch or native game validation.';startupMethod='late-crt-control';
    gateDeadlineMs=30000;observationLimitMs=120000;serverTotal=130000;editsWritten=0;relayAllocations=0;
    launcherSha256=(Get-FileHash "$output/BO3-Late-Control.exe").Hash.ToLowerInvariant();helperSha256=$pins['Bo3EnhancedHelper.dll'];gateSha256=$pins['Bo3StartupGate.dll'];
    files=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 6 | Set-Content "$output/build-receipt.json" -Encoding utf8
