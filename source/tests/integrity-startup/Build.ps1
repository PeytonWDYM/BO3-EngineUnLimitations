#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$FrozenJobBuild,
    [Parameter(Mandatory)][string]$FrozenIntegrityBuild,
    [Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
. (Join-Path $PSScriptRoot '../../launch/integrity_startup/Compile.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private owned output.'}
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no) -or
    (Get-FileHash $library).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC'){throw 'Use pinned unchanged Detours.'}
$prior=Get-Content (Join-Path $FrozenJobBuild 'result.json') -Raw | ConvertFrom-Json
if(!$prior.passed){throw 'Use a passing frozen owned job fixture.'}
$names=@('seed.bin','GameManifest.h','merged-inventory.json','Bo3EnhancedHelper.dll','Bo3StartupGate.dll',
    'VmStartupControlTarget.exe','RuntimeUnwindProfile.h','GateWaitProfile.h','TargetExports.h','BuildIdentity.h')
foreach($name in $names) {
    $file=Join-Path $FrozenJobBuild $name
    $row=@($prior.artifacts)+@($prior.files) | Where-Object {$_.Path -eq $file} | Select-Object -First 1
    if(!$row -or (Get-FileHash $file).Hash -ne $row.Hash){throw "The frozen fixture file differs: $name"}
}
$integrityPrior=Get-Content (Join-Path $FrozenIntegrityBuild 'result.json') -Raw | ConvertFrom-Json
if(!$integrityPrior.passed){throw 'Use a passing frozen authored integrity fixture.'}
$integrityNames=@('IntegrityOwnedImage.dll','Profile.h','fixture-seed.bin','fixture-seed.json')
foreach($name in $integrityNames) {
    $file=Join-Path $FrozenIntegrityBuild $name
    $row=@($integrityPrior.artifacts)+@($integrityPrior.sources) | Where-Object {$_.Path -eq $file} | Select-Object -First 1
    if(!$row -or (Get-FileHash $file).Hash -ne $row.Hash){throw "The authored integrity fixture differs: $name"}
}
New-Item -ItemType Directory -Path $output | Out-Null
foreach($name in $names){Copy-Item -LiteralPath (Join-Path $FrozenJobBuild $name) -Destination $output}
foreach($name in $integrityNames){Copy-Item -LiteralPath (Join-Path $FrozenIntegrityBuild $name) -Destination $output}
@('constexpr char kIntegrityProfileId[]="owned-inert-endpoints-1353";',
    'constexpr char kIntegrityOriginalDigest[]="owned-fixture-original";',
    'constexpr char kIntegrityReplacementDigest[]="owned-fixture-replacement";',
    "constexpr char kOwnedIntegrityImageHash[]=`"$((Get-FileHash "$output/IntegrityOwnedImage.dll").Hash.ToLowerInvariant())`";",
    "constexpr char kOwnedIntegritySeedHash[]=`"$((Get-FileHash "$output/fixture-seed.bin").Hash.ToLowerInvariant())`";") |
    Add-Content "$output/BuildIdentity.h" -Encoding ascii
$sources=Compile-IntegrityStartup -Repo $repo -Output $output -DetoursRoot $DetoursRoot -Owned
& $Python -B (Join-Path $repo 'source/launch/integrity_startup/Audit-Artifact.py') --directory $output --owned
if($LASTEXITCODE -ne 0){throw 'Owned integrity artifact audit failed.'}
$cases=@()
foreach($case in @('success','native-short','integrity-refusal','integrity-short','overlap','original','frame','rollback',
    'partial-write','rollback-failed','thaw','release','extra-thread','freeze-pending',
    'module-success','module-identity','module-guard','module-rollback')) {
    & "$output/IntegrityStartupOwnedFixture.exe" $case "$output/$case.json"
    if($LASTEXITCODE -ne 0){throw "Owned integrity case failed: $case"}
    $caseReceipt=Get-Content "$output/$case.json" -Raw | ConvertFrom-Json
    if($caseReceipt.receipt.startupMethod -ne 'late-crt-job-freeze-code-integrity' -or
        $caseReceipt.receipt.combinedEditsRequired -ne 1395 -or $caseReceipt.receipt.integrityProfile -ne 'owned-inert-endpoints-1353'){
        throw 'The owned receipt has the wrong method or profile.'
    }
    $cases+=$caseReceipt
}
$paths=@($sources)+@(Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName)
$paths+=Get-ChildItem (Join-Path $repo 'source/launch/integrity_startup') -File | ForEach-Object FullName
$paths+=Get-ChildItem (Join-Path $repo 'source/launch/job_startup') -File | Where-Object Extension -in @('.h','.cpp') | ForEach-Object FullName
$paths+=Get-ChildItem (Join-Path $repo 'source/launch/late_startup') -File | Where-Object Extension -in @('.h','.cpp') | ForEach-Object FullName
$paths+=@('source/launch/enhanced','source/launch/process_freeze','source/launch/startup_gate','source/launch/preentry',
    'source/patches/vm_startup','source/patches/vm_pool','source/patches/vm_migration','source/patches/code_integrity') |
    ForEach-Object {Get-ChildItem (Join-Path $repo $_) -File | Where-Object Extension -in @('.h','.cpp','.json') | ForEach-Object FullName}
$paths+=@($names | ForEach-Object {Join-Path $output $_})
$paths+=@($integrityNames | ForEach-Object {Join-Path $output $_})
$paths+=@($library,'C:\Windows\System32\ntdll.dll','C:\Windows\System32\kernel32.dll','C:\Windows\System32\KernelBase.dll')
@{passed=$true;scope='Owned exact job freeze and full42 preparation plus1353 inert endpoints or authored MEM_IMAGE module. Game checksum ownership remains unresolved.';
    cases=$cases;files=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash);
    artifacts=@(Get-ChildItem $output -File | Where-Object Extension -in @('.bin','.json','.exe','.dll') | Get-FileHash | Select-Object Path,Hash)} |
    ConvertTo-Json -Depth 9 | Set-Content "$output/result.json" -Encoding utf8
