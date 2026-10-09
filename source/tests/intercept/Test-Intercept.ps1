param([Parameter(Mandatory)][string]$OutputDirectory,
      [Parameter(Mandatory)][string]$DetoursRoot,
      [Parameter(Mandatory)][string]$Python, [string]$WindowsAuditDirectory)
$ErrorActionPreference = 'Stop'
# Resolve existing junctions before any compiler or output work.
function PhysicalPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $resolved = [IO.Path]::GetPathRoot($full)
    foreach ($part in $full.Substring($resolved.Length).Split([char[]]@('\', '/'), [StringSplitOptions]::RemoveEmptyEntries)) {
        $resolved = Join-Path $resolved $part
        if (Test-Path -LiteralPath $resolved) {
            $target = (Get-Item -LiteralPath $resolved).ResolveLinkTarget($true)
            if ($target) { $resolved = $target.FullName }
        }
    }
    return $resolved
}
$repo = PhysicalPath (Join-Path $PSScriptRoot '../../..')
$output = PhysicalPath $OutputDirectory
if ($output.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep fixture output outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Use a new evidence directory.' }
& (Join-Path $repo 'source/launch/intercept/Build-Intercept.ps1') -DetoursRoot $DetoursRoot -OutputDirectory (Join-Path $output 'bin') -WindowsAuditDirectory $WindowsAuditDirectory
& $Python -B (Join-Path $PSScriptRoot 'Verify-Intercept.py') --bin (Join-Path $output 'bin') --output (Join-Path $output 'results')
if ($LASTEXITCODE -ne 0) { throw 'The owned SDK memory E2E failed. Read results/result.json.' }
