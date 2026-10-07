param(
    [Parameter(Mandatory)][ValidateSet('Stage', 'Apply', 'Remove')][string]$Action,
    [Parameter(Mandatory)][string]$Directory,
    [string]$Target,
    [string]$Candidate
)
$ErrorActionPreference = 'Stop'
$originalHash = '30532F605E8B3C9914DCD1169B23F9D46CD83949FDFE5B5E0FBE2DDF361D1D88'
$candidateHash = 'AC4604A44D5CAF093DF917EB4A2A14C8979BFAB0088209122125FE09304C53F8'
function Assert-PlainTarget {
    param([Parameter(Mandatory)][string]$Path)
    $file = [IO.FileInfo]::new($Path)
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The target must not be a symbolic link.' }
    $parent = $file.Directory
    while ($null -ne $parent) {
        if ($parent.Exists -and ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'The target path must not contain junctions or symbolic links.'
        }
        $parent = $parent.Parent
    }
}
$lab = [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.codex\labs\bo3-engine'))
$directoryPath = [IO.Path]::GetFullPath($Directory)
if (!$directoryPath.StartsWith($lab + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep the deployment record inside the private BO3 lab.'
}
$ancestor = [IO.DirectoryInfo]::new($directoryPath)
while ($null -ne $ancestor) {
    if ($ancestor.Exists -and ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Use a deployment directory without junctions or symbolic links.'
    }
    $ancestor = $ancestor.Parent
}
$manifestPath = Join-Path $directoryPath 'deployment.json'
if ($Action -eq 'Stage') {
    if (!$Target -or !$Candidate) { throw 'Stage requires the target and candidate paths.' }
    if (Test-Path -LiteralPath $directoryPath) { throw 'Use a new deployment directory.' }
    $targetPath = (Resolve-Path -LiteralPath $Target).Path
    Assert-PlainTarget -Path $targetPath
    $candidatePath = (Resolve-Path -LiteralPath $Candidate).Path
    if ((Get-FileHash -LiteralPath $targetPath).Hash -ne $originalHash) { throw 'The target does not match the inspected original.' }
    if ((Get-FileHash -LiteralPath $candidatePath).Hash -ne $candidateHash) { throw 'The candidate does not match the verified artifact.' }
    New-Item -ItemType Directory -Path $directoryPath | Out-Null
    Copy-Item -LiteralPath $targetPath -Destination (Join-Path $directoryPath 'original.ff')
    Copy-Item -LiteralPath $candidatePath -Destination (Join-Path $directoryPath 'candidate.ff')
    if ((Get-FileHash -LiteralPath (Join-Path $directoryPath 'original.ff')).Hash -ne $originalHash) { throw 'Original backup verification failed.' }
    if ((Get-FileHash -LiteralPath (Join-Path $directoryPath 'candidate.ff')).Hash -ne $candidateHash) { throw 'Candidate backup verification failed.' }
    @{ Version = 1; Target = $targetPath; OriginalHash = $originalHash; CandidateHash = $candidateHash; Status = 'staged'; Utc = [datetimeoffset]::UtcNow.ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath $manifestPath
    Get-Content -LiteralPath $manifestPath
    return
}
if ([Diagnostics.Process]::GetProcessesByName('BlackOps3').Count -gt 0) { throw 'Close BO3 before applying or removing this experiment.' }
$record = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($record.Version -ne 1 -or $record.OriginalHash -ne $originalHash -or $record.CandidateHash -ne $candidateHash) {
    throw 'The deployment record has an unsupported identity.'
}
Assert-PlainTarget -Path $record.Target
if ($Action -eq 'Apply' -and (Get-FileHash -LiteralPath (Join-Path $directoryPath 'original.ff')).Hash -ne $originalHash) {
    throw 'The saved original is damaged. No file was replaced.'
}
$expected = if ($Action -eq 'Apply') { $originalHash } else { $candidateHash }
$desired = if ($Action -eq 'Apply') { $candidateHash } else { $originalHash }
$asset = Join-Path $directoryPath $(if ($Action -eq 'Apply') { 'candidate.ff' } else { 'original.ff' })
if ((Get-FileHash -LiteralPath $record.Target).Hash -ne $expected) { throw 'The current target has changed. No file was replaced.' }
if ((Get-FileHash -LiteralPath $asset).Hash -ne $desired) { throw 'The saved asset is damaged. No file was replaced.' }
# Replace the one asset atomically. The verified original remains in the lab.
$replacement = Join-Path $directoryPath ('replace-' + [guid]::NewGuid().ToString('N') + '.ff')
Copy-Item -LiteralPath $asset -Destination $replacement
[IO.File]::Replace($replacement, $record.Target, [NullString]::Value)
if ((Get-FileHash -LiteralPath $record.Target).Hash -ne $desired) { throw 'The replaced target failed verification.' }
$record.Status = if ($Action -eq 'Apply') { 'applied' } else { 'removed' }
$record.Utc = [datetimeoffset]::UtcNow.ToString('o')
$record | ConvertTo-Json | Set-Content -LiteralPath $manifestPath
Get-Content -LiteralPath $manifestPath
