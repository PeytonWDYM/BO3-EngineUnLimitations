[CmdletBinding()]
param([Parameter(Mandatory)][string]$PrivateDirectory)
$ErrorActionPreference='Stop'
function PhysicalPath([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path)
    $resolved=[IO.Path]::GetPathRoot($full)
    foreach($part in $full.Substring($resolved.Length).Split([char[]]@('\','/'),[StringSplitOptions]::RemoveEmptyEntries)) {
        $resolved=Join-Path $resolved $part
        if(Test-Path -LiteralPath $resolved) {
            $target=(Get-Item -LiteralPath $resolved).ResolveLinkTarget($true)
            if($target) { $resolved=$target.FullName }
        }
    }
    return $resolved
}
$repository=PhysicalPath (Join-Path $PSScriptRoot '../../..')
$private=PhysicalPath $PrivateDirectory
if ($private -eq $repository -or $private.StartsWith($repository+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Use a private directory outside the repository.' }
New-Item -ItemType Directory -Path $private -Force | Out-Null
$alias=Join-Path $private 'repository-alias'
New-Item -ItemType Junction -Path $alias -Target $repository | Out-Null
$suffix='audio-driver-guard-do-not-create'
$paths=@($repository,($repository.ToUpperInvariant()+'/'),(Join-Path $repository $suffix),(Join-Path $alias $suffix))
$savedPrograms=${env:ProgramFiles(x86)}
$results=@()
try {
    ${env:ProgramFiles(x86)}=Join-Path $private 'disabled-compiler-discovery'
    foreach($path in $paths) {
        $message=''
        try { & (Join-Path $PSScriptRoot 'Test-AudioDriver.ps1') -OutputDirectory $path } catch { $message=$_.Exception.Message }
        $rejected=$message -eq 'Write driver evidence outside the repository.'
        if(-not $rejected) { throw "Artifact guard did not reject $path before compiler discovery: $message" }
        $results+=@{path=$path;rejected=$rejected;failureStage='privacy-guard';newRepositoryChildExists=(Test-Path -LiteralPath (Join-Path $repository $suffix))}
    }
} finally { ${env:ProgramFiles(x86)}=$savedPrograms }
$results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $private 'artifact-guard.json') -Encoding utf8
if(Test-Path -LiteralPath (Join-Path $repository $suffix)) { throw 'The guard created a repository output directory.' }
