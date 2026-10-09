param(
    [Parameter(Mandatory)][string]$Source,
    [Parameter(Mandatory)][string]$Candidate,
    [Parameter(Mandatory)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$lab = [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.codex\labs\bo3-engine'))
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (!$output.StartsWith($lab + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Keep test output inside the private lab.' }
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory.' }
$ancestor = [IO.DirectoryInfo]::new($output)
while ($null -ne $ancestor) {
    if ($ancestor.Exists -and ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Use an output path without junctions.' }
    $ancestor = $ancestor.Parent
}
New-Item -ItemType Directory -Path $output | Out-Null
$manager = Join-Path $PSScriptRoot 'Manage-Candidate.ps1'
$sourceHash = (Get-FileHash -LiteralPath $Source).Hash
$candidateHash = (Get-FileHash -LiteralPath $Candidate).Hash
$target = Join-Path $output 'core_mod.ff'
Copy-Item -LiteralPath $Source -Destination $target
'unchanged sibling' | Set-Content -LiteralPath (Join-Path $output 'sibling.txt')
$siblingHash = (Get-FileHash -LiteralPath (Join-Path $output 'sibling.txt')).Hash
$record = Join-Path $output 'record'
& $manager -Action Stage -Directory $record -Target $target -Candidate $Candidate | Set-Content -LiteralPath (Join-Path $output 'stage.json')
$backup = Join-Path $record 'original.ff'
$damaged = [IO.File]::ReadAllBytes($backup)
$damaged[0] = $damaged[0] -bxor 1
[IO.File]::WriteAllBytes($backup, $damaged)
$beforeApplyRejected = $false
try { & $manager -Action Apply -Directory $record } catch { $beforeApplyRejected = $_.Exception.Message.Contains('saved original is damaged') }
if (!$beforeApplyRejected -or (Get-FileHash -LiteralPath $target).Hash -ne $sourceHash) { throw 'Pre-apply backup guard failed.' }
Copy-Item -LiteralPath $Source -Destination $backup
& $manager -Action Apply -Directory $record | Set-Content -LiteralPath (Join-Path $output 'apply.json')
if ((Get-FileHash -LiteralPath $target).Hash -ne $candidateHash) { throw 'Apply produced the wrong target hash.' }
$repeatRejected = $false
try { & $manager -Action Apply -Directory $record } catch { $repeatRejected = $_.Exception.Message.Contains('current target has changed') }
if (!$repeatRejected) { throw 'Repeated apply did not fail.' }
$damaged = [IO.File]::ReadAllBytes($backup)
$damaged[0] = $damaged[0] -bxor 1
[IO.File]::WriteAllBytes($backup, $damaged)
$damageRejected = $false
try { & $manager -Action Remove -Directory $record } catch { $damageRejected = $_.Exception.Message.Contains('saved asset is damaged') }
if (!$damageRejected -or (Get-FileHash -LiteralPath $target).Hash -ne $candidateHash) { throw 'Damaged backup guard failed.' }
Copy-Item -LiteralPath $Source -Destination $backup
& $manager -Action Remove -Directory $record | Set-Content -LiteralPath (Join-Path $output 'remove.json')
if ((Get-FileHash -LiteralPath $target).Hash -ne $sourceHash) { throw 'Removal did not restore the exact original.' }
if ((Get-FileHash -LiteralPath (Join-Path $output 'sibling.txt')).Hash -ne $siblingHash) { throw 'A sibling file changed.' }
if ((Get-FileHash -LiteralPath $Source).Hash -ne $sourceHash) { throw 'The source changed.' }
@{ Status = 'passed'; AppliedSha256 = $candidateHash; RestoredSha256 = $sourceHash; RepeatedApplyRejected = $repeatRejected; DamagedBackupBeforeApplyRejected = $beforeApplyRejected; DamagedBackupBeforeRemovalRejected = $damageRejected; SourceAndSiblingUnchanged = $true; ManagerSha256 = (Get-FileHash -LiteralPath $manager).Hash } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'result.json')
Get-Content -LiteralPath (Join-Path $output 'result.json')
