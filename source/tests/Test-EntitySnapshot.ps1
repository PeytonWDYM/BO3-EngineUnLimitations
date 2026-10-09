[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\','/')
if ($output -eq $repo -or $output.StartsWith($repo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Write snapshot artifacts outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Choose a new E2E output directory.' }
& (Join-Path $repo 'source/launch/Build-Tools.ps1') -OutputDirectory (Join-Path $output 'bin')
$fixture = Join-Path $output 'bin/PoolFixture.exe'
$target = Start-Process -FilePath $fixture -WindowStyle Hidden -PassThru
$dumpJob = $null
try {
    Start-Sleep -Milliseconds 300
    [PSCustomObject]@{
        pid=$target.Id
        startedUtc=$target.StartTime.ToUniversalTime().ToString('o')
        sha256=(Get-FileHash -LiteralPath $fixture -Algorithm SHA256).Hash
        executable=$fixture
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'identity.json') -Encoding utf8
    Import-Module (Join-Path $repo 'source/Dumps.psm1') -Force
    $dumpJob = Start-ProcessDump -Tool (Join-Path $repo 'tools/procdump/procdump64.exe') -TargetId $target.Id -Session $output
    if (-not $dumpJob.Process.WaitForExit(45000)) { throw 'The fixture snapshot timed out.' }
    $dump = Complete-ProcessDump -Job $dumpJob
    $dumpJob = $null
    if (-not $dump.complete) { throw 'The fixture snapshot is incomplete.' }
    & $Python (Join-Path $PSScriptRoot 'Verify-EntitySnapshot.py') --dump $dump.path --fixture $fixture --output $output
    if ($LASTEXITCODE -ne 0) { throw 'Entity snapshot E2E failed.' }
} finally {
    if ($null -ne $dumpJob -and -not $dumpJob.Process.HasExited) { $dumpJob.Process.Kill() }
    if (-not $target.HasExited) { $target.Kill() }
}
