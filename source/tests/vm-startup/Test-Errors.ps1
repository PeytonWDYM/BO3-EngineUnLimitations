param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$output=[IO.Path]::GetFullPath($OutputDirectory)
& (Join-Path $PSScriptRoot 'Build-Errors.ps1') -OutputDirectory (Join-Path $output 'bin')
$runner=Join-Path $output 'bin/VmErrorFixture.exe'
$sources=@(Get-ChildItem -LiteralPath $PSScriptRoot -File; Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../../patches/vm_startup') -File) | Get-FileHash | Select-Object Path,Hash
$before=(Get-FileHash -LiteralPath $runner).Hash
$cases=@('read-success','write-success','read-errors','write-errors','arguments','decode-error','later-read','later-arguments','suppress','unwind')
$receipts=foreach($case in $cases) {
    $path=Join-Path $output "$case.json"
    & $runner $case $path
    if($LASTEXITCODE -ne 0) { throw "Owned error case failed: $case" }
    Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}
if((Get-FileHash -LiteralPath $runner).Hash -ne $before) { throw 'Owned binary changed during the test.' }
$after=@(Get-ChildItem -LiteralPath $PSScriptRoot -File; Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../../patches/vm_startup') -File) | Get-FileHash | Select-Object Path,Hash
if(Compare-Object $sources $after -Property Path,Hash) { throw 'Fixture sources changed during the test.' }
@{ scope='Owned Windows error entry and SEH exit only. Later detour models saved MinHook jump relocation. No BO3 or AAE execution.';
    caseCount=$receipts.Count; binarySha256=$before; recoveredEntry5='4c894c2420'; receipts=$receipts; sources=$sources
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output 'result.json') -Encoding utf8
