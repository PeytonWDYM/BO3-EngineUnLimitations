#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$ProductionBuild,
    [Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..')
$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep diagnostic builds outside the repository.' }
if(Test-Path -LiteralPath $output) { throw 'Use a new diagnostic directory.' }
$production=PhysicalPath $ProductionBuild
$DetoursRoot=PhysicalPath $DetoursRoot
if((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no)) { throw 'Use unchanged official Detours v4.0.1.' }
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if((Get-FileHash -LiteralPath $library).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC') { throw 'The pinned Detours library differs.' }
$receipt=Get-Content -LiteralPath (Join-Path $production 'build-receipt.json') -Raw | ConvertFrom-Json
$helper=Join-Path $production 'Bo3EnhancedHelper.dll'
if((Get-FileHash -LiteralPath $helper).Hash.ToLowerInvariant() -ne $receipt.helperSha256.ToLowerInvariant()) { throw 'Production helper identity differs.' }
New-Item -ItemType Directory -Path $output | Out-Null
Copy-Item -LiteralPath $helper -Destination (Join-Path $output 'Bo3EnhancedHelper.dll')
Copy-Item -LiteralPath (Join-Path $production 'Detours-LICENSE.md') -Destination $output
$header=Join-Path $output 'BuildIdentity.h'
$repoLiteral=$repo.Replace('\','\\')
@('#pragma once',"constexpr wchar_t kRepositoryRoot[]=L`"$repoLiteral`";",'constexpr char kGameHash[]="0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0";',
    "constexpr char kHelperHash[]=`"$($receipt.helperSha256.ToLowerInvariant())`";") | Set-Content -LiteralPath $header -Encoding ascii
& $Python -B (Join-Path $repo 'source/tests/vm-startup/Control-Profile.py') --helper (Join-Path $output 'Bo3EnhancedHelper.dll') --output (Join-Path $output 'ControlProfile.h')
if($LASTEXITCODE -ne 0) { throw 'Diagnostic profile generation failed.' }
& (Join-Path $repo 'source/tests/vm-startup/Compile-StartupControl.ps1') -OutputDirectory $output -DetoursRoot $DetoursRoot
if($LASTEXITCODE -ne 0) { throw 'Diagnostic compilation failed.' }
$paths=@(Get-ChildItem $output -File | Where-Object Extension -in '.exe','.dll','.h')
$inputs=@('StartupControl.h','StartupControl.cpp','StartupObservation.h','StartupObservation.cpp','StartupPassive.cpp','StartupDiagnostic.cpp','Build-StartupDiagnostic.ps1','SteamContext.cpp','SteamContext.h','LaunchLease.h','Boot.h','PhysicalPath.ps1')
$paths+=@($inputs | ForEach-Object { Get-Item -LiteralPath (Join-Path $PSScriptRoot $_) })
$paths+=@(Get-Item -LiteralPath (Join-Path $repo 'source/launch/preentry/Identity.cpp'),(Join-Path $repo 'source/launch/preentry/Identity.h'),
    (Join-Path $repo 'source/tests/vm-startup/Compile-StartupControl.ps1'),(Join-Path $repo 'source/tests/vm-startup/Control-Profile.py'),
    (Join-Path $DetoursRoot 'include/detours.h'),$library)
@{scope='Exact-build startup diagnostic only. No DR or VM writes; not an enhanced readiness receipt.'; detoursCommit='e4bfd6b03e50de46b47abfbd1e46b384f0c5f833'; files=@($paths | Get-FileHash | Select-Object Path,Hash)} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output 'diagnostic-build-receipt.json') -Encoding utf8
