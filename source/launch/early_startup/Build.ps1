#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$VmBuild,
    [Parameter(Mandatory)][string]$GateBuild,[Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../enhanced/PhysicalPath.ps1')
. (Join-Path $PSScriptRoot 'Compile.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private build directory.'}
New-Item -ItemType Directory -Path $output | Out-Null
# The existing builder checks the frozen helper, gate, Detours and native recipe.
& (Join-Path $PSScriptRoot '../job_startup/Build.ps1') -OutputDirectory "$output/base" -VmBuild $VmBuild -GateBuild $GateBuild -DetoursRoot $DetoursRoot -Python $Python
if($LASTEXITCODE -ne 0){throw 'The original native recipe build failed.'}
$base=Get-Content "$output/base/build-receipt.json" -Raw | ConvertFrom-Json
$names=@('Bo3EnhancedHelper.dll','Bo3StartupGate.dll','BuildIdentity.h','GameManifest.h','GateWaitProfile.h','RuntimeUnwindProfile.h','Detours-LICENSE.md')
foreach($name in $names){Copy-Item -LiteralPath "$output/base/$name" -Destination $output}
$digest=[Convert]::FromHexString('0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0')
@('#include <array>',('constexpr std::array<unsigned char,32> kVerifiedGameDigest{'+(($digest | ForEach-Object {'0x'+$_.ToString('x2')}) -join ',')+'};')) |
    Add-Content "$output/BuildIdentity.h" -Encoding ascii
& $Python -B (Join-Path $repo 'source/patches/early_integrity/Generate-Profile.py') --output "$output/EarlyIntegrityProfile.h"
if($LASTEXITCODE -ne 0){throw 'The exact early checksum profile differs.'}
$sources=Compile-EarlyStartup -Repo $repo -Output $output -DetoursRoot $DetoursRoot
& $Python -B (Join-Path $PSScriptRoot 'Audit-Artifact.py') --directory $output
if($LASTEXITCODE -ne 0){throw 'The 500K launcher artifact audit failed.'}
$paths=@($sources)+@(Get-ChildItem $PSScriptRoot -File | Where-Object {
    $_.Extension -in @('.h','.cpp','.ps1') -or $_.Name -in @('Audit-Artifact.py','Contract.txt')
} | ForEach-Object FullName)
$paths+=Get-ChildItem (Join-Path $repo 'source/patches/early_integrity') -File | ForEach-Object FullName
$paths+=@($base.files.Path)+@($names | ForEach-Object {Join-Path $output $_})+@("$output/EarlyIntegrityProfile.h","$output/artifact-audit.json","$output/base/build-receipt.json")
@{scope='Experimental 500K startup with early checksum correction. Live startup remains unvalidated.';
    startupMethod='late-crt-job-freeze-early-checksum';deadlineMs=30000;serverTotal=500001;clientRoots=18;migrationBufferBytes=33554432;
    liveStartupValidated=$false;checksumReapplication=$false;
    launcherSha256=(Get-FileHash "$output/BO3-500K-Zombies.exe").Hash;helperSha256=$base.helperSha256;gateSha256=$base.gateSha256;
    files=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 7 |
    Set-Content "$output/build-receipt.json" -Encoding utf8
