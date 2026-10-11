#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../../../scripts/release/Platform.ps1')
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$output = [IO.Path]::GetFullPath($OutputDirectory)
if ((Test-Path -LiteralPath $output) -or (Test-WithinPath $output $repo)) {
    throw 'Use a new output directory outside the repository.'
}
New-Item -ItemType Directory -Path $output | Out-Null
$root = Join-Path $output 'Owned Folder'
$cases = @(
    @{name='root'; path=$root; expected=$true},
    @{name='child'; path=(Join-Path $root 'child'); expected=$true},
    @{name='sibling-prefix'; path=($root + '-other'); expected=$false},
    @{name='case-distinct-folder'; path=$root.ToUpperInvariant(); expected=$IsWindows},
    @{name='dot-escape'; path=(Join-Path $root '../outside'); expected=$false},
    @{name='dot-entry'; path=(Join-Path $output 'outside/../Owned Folder/child'); expected=$true}
) | ForEach-Object {
    $actual = Test-WithinPath $_.path $root
    @{name=$_.name; expected=$_.expected; actual=$actual; passed=($actual -eq $_.expected)}
}
$passed = !($cases | Where-Object { !$_.passed })
@{passed=$passed; platform=[Environment]::OSVersion.Platform.ToString(); cases=$cases
  scope='Filesystem path comparisons. No build, game launch, or Steam changes.'
  helperSha256=(Get-FileHash (Join-Path $PSScriptRoot '../../../scripts/release/Platform.ps1')).Hash
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output 'result.json')
Write-Host "$(@($cases | Where-Object passed).Count)/$($cases.Count) platform path cases passed."
if (!$passed) { exit 1 }
