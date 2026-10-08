param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory)
& (Join-Path $PSScriptRoot 'Build.ps1') -OutputDirectory (Join-Path $output 'bin')
$runner = Join-Path $output 'bin/VmStartupFixture.exe'
$cases = @(
    @('baseline',130000), @('entry',500001), @('entry',1000001),
    @('tls',500001), @('tls',1000001), @('worker',1000001),
    @('concurrent',500001), @('concurrent',1000001), @('client-first',1000001),
    @('mismatch',1000001), @('existing',1000001), @('repeated',1000001), @('existing-hash',1000001),
    @('foreign',1000001), @('no-call',1000001), @('fault',1000001),
    @('single-step',1000001), @('trace-gate',1000001)
)
$receipts = foreach ($case in $cases) {
    $path = Join-Path $output "$($case[0])-$($case[1]).json"
    & $runner $case[0] $case[1] $path | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Owned startup case failed: $($case[0])" }
    Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}
@{
    scope = 'Fixed owned Windows child only. Debugger remains attached through exit. No BO3 launch or game profile.'
    caseCount = $receipts.Count
    receipts = $receipts
    sources = @(Get-ChildItem -LiteralPath $PSScriptRoot -File; Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../../patches/vm_startup') -File) |
        Get-FileHash | Select-Object Path,Hash
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output 'result.json') -Encoding utf8
