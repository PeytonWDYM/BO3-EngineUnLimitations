param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$DetoursRoot,[Parameter(Mandatory)][string]$Python,[switch]$ProductionHelper)
$ErrorActionPreference='Stop'
$output=[IO.Path]::GetFullPath($OutputDirectory)
& (Join-Path $PSScriptRoot 'Build.ps1') -OutputDirectory (Join-Path $output 'bin') -DetoursRoot $DetoursRoot -NativeComposition -ProductionHelper:$ProductionHelper
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$inventoryArguments = @()
if ($ProductionHelper) { $inventoryArguments += '--production' }
& $Python (Join-Path $PSScriptRoot 'Inspect-Helper.py') --bin (Join-Path $output 'bin') --dumpbin (Join-Path $compilerRoot 'bin/Hostx64/x64/dumpbin.exe') --output (Join-Path $output 'loader-inventory.json') @inventoryArguments
if($LASTEXITCODE -ne 0) { throw 'Composed native helper inventory failed.' }
$runner=Join-Path $output 'bin/VmNativeFixture.exe'
$binaries=Get-ChildItem -LiteralPath (Join-Path $output 'bin') -File | Where-Object Extension -In '.exe','.dll' | Get-FileHash | Select-Object Path,Hash
$sourceFiles=@(Get-ChildItem -LiteralPath $PSScriptRoot -File; Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../../patches/vm_startup') -File;
    Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../../patches/vm_pool') -File;
    Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../../launch/enhanced') -File)
$sources=$sourceFiles | Get-FileHash | Select-Object Path,Hash
$cases=@(@('roundtrip',500001),@('roundtrip',1000001),@('decode-error',500001),@('state-error',500001),@('later-error',500001),
    @('rollback',500001),@('entry-mismatch',500001),@('far-relay',500001))
if ($ProductionHelper) { $cases += @(@('boot-invalid',500001),@('boot-not-ready',500001)) }
$receipts=foreach($case in $cases) {
    $path=Join-Path $output "$($case[0])-$($case[1]).json"
    & $runner $case[0] $case[1] $path | Out-Host
    if($LASTEXITCODE -ne 0) { throw "Owned native composition failed: $($case[0])" }
    Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}
if ($ProductionHelper) {
    $bootPath = Join-Path $output 'production-boot.json'
    & (Join-Path $output 'bin/VmProductionBootFixture.exe') $bootPath | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Production helper failed without fixture inputs.' }
    $receipts += Get-Content -LiteralPath $bootPath -Raw | ConvertFrom-Json
}
$savedCases=@(@('helper-tls',500001),@('helper-concurrent',1000001),@('helper-ready-denied',500001),@('helper-hook-mismatch',500001),
    @('helper-dirty-binding',500001),@('helper-missing-readiness',500001),@('helper-absent',500001))
if ($ProductionHelper) { $savedCases = @() }
$savedReceipts=foreach($case in $savedCases) {
    $path=Join-Path $output "$($case[0])-$($case[1]).json"
    & (Join-Path $output 'bin/VmStartupFixture.exe') $case[0] $case[1] $path | Out-Host
    if($LASTEXITCODE -ne 0) { throw "Saved helper-contract case failed: $($case[0])" }
    Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}
@{ scope='Selected earlier loader/TLS/concurrency/refusal cases against the composed helper binary.';
    caseCount=$savedReceipts.Count; receipts=$savedReceipts
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output 'saved-cases.json') -Encoding utf8
$after=Get-ChildItem -LiteralPath (Join-Path $output 'bin') -File | Where-Object Extension -In '.exe','.dll' | Get-FileHash | Select-Object Path,Hash
if(Compare-Object $binaries $after -Property Path,Hash) { throw 'Owned composed binaries changed during testing.' }
if(Compare-Object $sources ($sourceFiles | Get-FileHash | Select-Object Path,Hash) -Property Path,Hash) { throw 'Composed native sources changed during testing.' }
@{ scope='Fixed debug-paused owned child with real helper state/error exports and owned native continuations. No BO3/AAE execution.';
    caseCount=$receipts.Count; receipts=$receipts; sources=$sources; binaries=$binaries
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output 'result.json') -Encoding utf8
