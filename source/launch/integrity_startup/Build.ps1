#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$VmBuild,
    [Parameter(Mandatory)][string]$GateBuild,[Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../enhanced/PhysicalPath.ps1')
. (Join-Path $PSScriptRoot 'Compile.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private build directory.'}
New-Item -ItemType Directory -Path $output | Out-Null
# The existing builder admits the pinned helper, gate, Detours and complete native recipe.
& (Join-Path $PSScriptRoot '../job_startup/Build.ps1') -OutputDirectory "$output/base" -VmBuild $VmBuild -GateBuild $GateBuild -DetoursRoot $DetoursRoot -Python $Python
if($LASTEXITCODE -ne 0){throw 'The original job recipe build failed.'}
$base=Get-Content "$output/base/build-receipt.json" -Raw | ConvertFrom-Json
$names=@('Bo3EnhancedHelper.dll','Bo3StartupGate.dll','BuildIdentity.h','GameManifest.h','GateWaitProfile.h','RuntimeUnwindProfile.h','Detours-LICENSE.md')
foreach($name in $names){Copy-Item -LiteralPath "$output/base/$name" -Destination $output}
$digest=[Convert]::FromHexString('0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0')
@('#include <array>',('constexpr std::array<unsigned char,32> kVerifiedGameDigest{'+(($digest | ForEach-Object {'0x'+$_.ToString('x2')}) -join ',')+'};')) |
    Add-Content "$output/BuildIdentity.h" -Encoding ascii
& $Python -B (Join-Path $repo 'source/patches/code_integrity/Generate-Profile.py') --output "$output/Profile.h"
if($LASTEXITCODE -ne 0){throw 'The exact integrity profile differs.'}
$sources=Compile-IntegrityStartup -Repo $repo -Output $output -DetoursRoot $DetoursRoot
& $Python -B (Join-Path $PSScriptRoot 'Audit-Artifact.py') --directory $output
if($LASTEXITCODE -ne 0){throw 'The integrity startup artifact audit failed.'}
$paths=@($sources)+@(Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName)
$paths+=Get-ChildItem (Join-Path $repo 'source/patches/code_integrity') -File | ForEach-Object FullName
$paths+=@($base.files.Path)+@($names | ForEach-Object {Join-Path $output $_})+@("$output/Profile.h","$output/artifact-audit.json","$output/base/build-receipt.json")
$planHeader=Get-Content (Join-Path $repo 'source/patches/code_integrity/Plan.h') -Raw
$attribution=[regex]::Match($planHeader,'kProductionInputAttributionVerified=(true|false);')
if(!$attribution.Success){throw 'The fixed module attribution state is missing.'}
$profileHeader=Get-Content (Join-Path $repo 'source/patches/code_integrity/ProfileIdentity.h') -Raw
$profile=[regex]::Match($profileHeader,'kProfileId\[\]="([0-9a-f]{64})"')
if(!$profile.Success){throw 'The fixed module profile identity is missing.'}
@{scope='Experimental optional combined integrity and500k startup recipe. No game startup or allocation validation.';
    startupMethod='late-crt-job-freeze-code-integrity';deadlineMs=30000;nativeEdits=42;integrityEdits=1353;combinedEdits=1395;
    integrityProfile=$profile.Groups[1].Value;integrityInputAttributionVerified=($attribution.Groups[1].Value -eq 'true');liveStartupValidated=$false;
    launcherSha256=(Get-FileHash "$output/BO3-Integrity-Zombies.exe").Hash;helperSha256=$base.helperSha256;gateSha256=$base.gateSha256;
    files=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 7 |
    Set-Content "$output/build-receipt.json" -Encoding utf8
