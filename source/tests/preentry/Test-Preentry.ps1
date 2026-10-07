param(
    [Parameter(Mandatory)][string]$DetoursRoot,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
if ($output.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep pre-entry evidence outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Use a new evidence directory.' }
& (Join-Path $PSScriptRoot '../../launch/preentry/Build-Preentry.ps1') -DetoursRoot $DetoursRoot -OutputDirectory (Join-Path $output 'bin')
& $Python (Join-Path $PSScriptRoot 'Verify-Preentry.py') --bin (Join-Path $output 'bin') --output (Join-Path $output 'results')
if ($LASTEXITCODE -ne 0) { throw 'The owned pre-entry E2E failed. See results/result.json.' }
