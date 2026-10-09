#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$FrozenJobBuild,
    [Parameter(Mandatory)][string]$FrozenChecksumBuild,[Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
. (Join-Path $PSScriptRoot '../../launch/early_startup/Compile.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private proof directory.'}
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no) -or
    (Get-FileHash $library).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC'){throw 'Use pinned unchanged Detours.'}
$job=Get-Content (Join-Path $FrozenJobBuild 'result.json') -Raw | ConvertFrom-Json
$checksum=Get-Content (Join-Path $FrozenChecksumBuild 'result.json') -Raw | ConvertFrom-Json
if(!$job.passed -or !$checksum.passed){throw 'Use passing frozen job and checksum fixtures.'}
$jobNames=@('seed.bin','GameManifest.h','Bo3EnhancedHelper.dll','Bo3StartupGate.dll','VmStartupControlTarget.exe',
    'RuntimeUnwindProfile.h','GateWaitProfile.h','TargetExports.h','BuildIdentity.h')
$checksumNames=@('EarlyIntegrityOwnedImage.dll','EarlyIntegrityProfile.h')
foreach($pair in @(@{root=$FrozenJobBuild;receipt=$job;names=$jobNames},@{root=$FrozenChecksumBuild;receipt=$checksum;names=$checksumNames})) {
    foreach($name in $pair.names) {
        $path=Join-Path $pair.root $name
        $row=@($pair.receipt.artifacts)+@($pair.receipt.files)+@($pair.receipt.sources) | Where-Object Path -EQ $path | Select-Object -First 1
        if(!$row -or (Get-FileHash -LiteralPath $path).Hash -ne $row.Hash){throw "A frozen proof file differs: $name"}
    }
}
New-Item -ItemType Directory -Path $output | Out-Null
foreach($name in $jobNames){Copy-Item -LiteralPath (Join-Path $FrozenJobBuild $name) -Destination $output}
foreach($name in $checksumNames){Copy-Item -LiteralPath (Join-Path $FrozenChecksumBuild $name) -Destination $output}
"constexpr char kOwnedChecksumImageHash[]=`"$((Get-FileHash "$output/EarlyIntegrityOwnedImage.dll").Hash.ToLowerInvariant())`";" |
    Add-Content "$output/BuildIdentity.h" -Encoding ascii
$sources=Compile-EarlyStartup -Repo $repo -Output $output -DetoursRoot $DetoursRoot -Owned
& $Python -B (Join-Path $repo 'source/launch/early_startup/Audit-Artifact.py') --directory $output --owned
if($LASTEXITCODE -ne 0){throw 'The owned startup artifact audit failed.'}
$cases=@()
foreach($case in @('success','native-short','checksum-short','identity','context','original','overlap','frame','rollback','thaw','release')) {
    & "$output/EarlyStartupOwned.exe" $case "$output/$case.json"
    if($LASTEXITCODE -ne 0){throw "Owned early startup case failed: $case"}
    $cases+=Get-Content "$output/$case.json" -Raw | ConvertFrom-Json
}
$paths=@($sources)+@(Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName)
$paths+=@('source/launch/early_startup','source/launch/job_startup','source/launch/late_startup','source/patches/early_integrity') |
    ForEach-Object {Get-ChildItem (Join-Path $repo $_) -File | Where-Object Extension -in @('.h','.cpp','.json','.py','.ps1','.txt','.md') | ForEach-Object FullName}
$paths+=@($jobNames+$checksumNames | ForEach-Object {Join-Path $output $_})+@($library,'C:\Windows\System32\ntdll.dll',
    (Join-Path $repo 'source/tests/early-integrity/Fixture.h'))
@{passed=$true;scope='Complete native42 and early checksum transaction in owned inert images. No game or Steam execution.';
    cases=$cases;files=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash);
    artifacts=@(Get-ChildItem $output -File | Where-Object Extension -in @('.bin','.json','.exe','.dll','.h') | Get-FileHash | Select-Object Path,Hash)} |
    ConvertTo-Json -Depth 8 | Set-Content "$output/result.json" -Encoding utf8
