#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$FrozenJobBuild,
    [Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
. (Join-Path $PSScriptRoot '../../launch/integrity_startup/Compile.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private resource proof directory.'}
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no) -or
    (Get-FileHash $library).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC'){throw 'Use pinned unchanged Detours.'}
$prior=Get-Content (Join-Path $FrozenJobBuild 'result.json') -Raw | ConvertFrom-Json
if(!$prior.passed){throw 'Use the passing frozen owned native image.'}
$names=@('seed.bin','GameManifest.h','Bo3EnhancedHelper.dll','Bo3StartupGate.dll','VmStartupControlTarget.exe',
    'RuntimeUnwindProfile.h','GateWaitProfile.h','TargetExports.h','BuildIdentity.h')
foreach($name in $names) {
    $file=Join-Path $FrozenJobBuild $name
    $row=@($prior.artifacts)+@($prior.files) | Where-Object {$_.Path -eq $file} | Select-Object -First 1
    if(!$row -or (Get-FileHash $file).Hash -ne $row.Hash){throw "The frozen owned file differs: $name"}
}
New-Item -ItemType Directory -Path $output | Out-Null
foreach($name in $names){Copy-Item -LiteralPath (Join-Path $FrozenJobBuild $name) -Destination $output}
$sources=Compile-IntegrityStartup -Repo $repo -Output $output -DetoursRoot $DetoursRoot -Owned -Resources
& $Python -B (Join-Path $repo 'source/launch/integrity_startup/Audit-Artifact.py') --directory $output --owned --resources
if($LASTEXITCODE -ne 0){throw 'The resource fixture artifact audit failed.'}
$cases=@()
foreach($case in @('success','rollback','plan-refusal','thaw','release')) {
    & "$output/NativePublicationResourcesOwned.exe" $case "$output/$case.json"
    if($LASTEXITCODE -ne 0){throw "Owned resource case failed: $case"}
    $cases+=Get-Content "$output/$case.json" -Raw | ConvertFrom-Json
}
$paths=@($sources)+@(Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName)
$paths+=@('source/launch/job_startup','source/launch/late_startup','source/launch/enhanced','source/launch/preentry',
    'source/launch/process_freeze','source/launch/startup_gate','source/patches/vm_startup','source/patches/vm_pool','source/patches/vm_migration') |
    ForEach-Object {Get-ChildItem (Join-Path $repo $_) -File | Where-Object Extension -in @('.h','.cpp','.json') | ForEach-Object FullName}
$paths+=@($names | ForEach-Object {Join-Path $output $_})+@($library,'C:\Windows\System32\ntdll.dll',
    (Join-Path $repo 'source/launch/integrity_startup/Compile.ps1'),(Join-Path $repo 'source/launch/integrity_startup/Audit-Artifact.py'))
@{passed=$true;scope='Owned extra resource lifetime under reviewed native42 transaction. No store-correction or game validation.';
    cases=$cases;files=@($paths | Sort-Object -Unique | Get-FileHash | Select-Object Path,Hash);
    artifacts=@(Get-ChildItem $output -File | Where-Object Extension -in @('.bin','.json','.exe','.dll') | Get-FileHash | Select-Object Path,Hash)} |
    ConvertTo-Json -Depth 8 | Set-Content "$output/result.json" -Encoding utf8
