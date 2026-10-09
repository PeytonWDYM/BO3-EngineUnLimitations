param([Parameter(Mandatory)][string]$OutputDirectory, [Parameter(Mandatory)][string]$DetoursRoot,
    [Parameter(Mandatory)][string]$Python)
$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory)
$bin = Join-Path $output 'bin'
& (Join-Path $PSScriptRoot 'Build.ps1') -OutputDirectory $bin -DetoursRoot $DetoursRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot = (Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
& $Python -B (Join-Path $PSScriptRoot 'Inspect-Helper.py') --bin $bin --dumpbin (Join-Path $compilerRoot 'bin/Hostx64/x64/dumpbin.exe') --output (Join-Path $output 'loader-inventory.json')
if ($LASTEXITCODE -ne 0) { throw 'Owned helper loader inventory failed.' }
$runner = Join-Path $bin 'VmStartupFixture.exe'
$before = @(Get-ChildItem -LiteralPath $bin -Filter *.exe; Get-ChildItem -LiteralPath $bin -Filter *.dll) | Get-FileHash
$cases = @(
    @('baseline',130000), @('helper-entry',500001), @('helper-entry',1000001),
    @('helper-tls',500001), @('helper-tls',1000001), @('helper-worker',1000001),
    @('helper-concurrent',500001), @('helper-concurrent',1000001), @('helper-client-first',1000001),
    @('helper-missing-readiness',1000001), @('helper-absent',1000001), @('helper-dirty-binding',1000001),
    @('helper-hook-mismatch',1000001), @('helper-ready-denied',1000001), @('helper-trace-gate',1000001)
)
$receipts = foreach ($case in $cases) {
    $path = Join-Path $output "$($case[0])-$($case[1]).json"
    & $runner $case[0] $case[1] $path | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Owned composition case failed: $($case[0])" }
    Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}
$tampered = Join-Path $output 'tampered-helper'
New-Item -ItemType Directory -Path $tampered | Out-Null
Get-ChildItem -LiteralPath $bin -File | Where-Object { $_.Extension -in '.exe','.dll' } | Copy-Item -Destination $tampered
$helperPath = Join-Path $tampered 'VmStartupHelper.dll'
$bytes = [IO.File]::ReadAllBytes($helperPath)
$bytes[$bytes.Length-1] = $bytes[$bytes.Length-1] -bxor 1
[IO.File]::WriteAllBytes($helperPath,$bytes)
$identityOutput = Join-Path $output 'wrong-identity.json'
& (Join-Path $tampered 'VmStartupFixture.exe') helper-entry 500001 $identityOutput 2> (Join-Path $output 'wrong-identity.stderr.txt') | Out-Host
$identityExit = $LASTEXITCODE
if ($identityExit -eq 0 -or (Test-Path -LiteralPath $identityOutput)) { throw 'Wrong helper identity did not refuse before child creation.' }
$after = @(Get-ChildItem -LiteralPath $bin -Filter *.exe; Get-ChildItem -LiteralPath $bin -Filter *.dll) | Get-FileHash
if (Compare-Object ($before | Select-Object Path,Hash) ($after | Select-Object Path,Hash) -Property Path,Hash) { throw 'Owned binaries changed.' }
@{
    scope = 'Pre-imported fixed owned helper. Parent writes POD bindings and owned callback hooks while debugpaused. No captured game serializer or BO3 launch.'
    caseCount = $receipts.Count + 1
    receipts = $receipts
    wrongIdentityExit = $identityExit
    before = $before | Select-Object Path,Hash
    after = $after | Select-Object Path,Hash
    sources = @(Get-ChildItem -LiteralPath $PSScriptRoot -File; Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../../patches/vm_startup') -File;
        Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../../patches/vm_pool') -File) | Get-FileHash | Select-Object Path,Hash
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $output 'result.json') -Encoding utf8
