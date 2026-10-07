[CmdletBinding()]
param(
    [string]$GameDirectory = '',
    [string]$OutputRoot = ''
)

$ErrorActionPreference = 'Stop'
if (-not $OutputRoot) { $OutputRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'research/captures/live' }
$procdump = Join-Path (Split-Path $PSScriptRoot -Parent) 'tools/procdump/procdump64.exe'
if (-not (Test-Path -LiteralPath $procdump)) { throw 'Run source/Install-Tools.ps1 before starting a capture.' }
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$shell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$script = Join-Path $PSScriptRoot 'Monitor.ps1'
$arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -OutputRoot "{1}"' -f $script, $OutputRoot
if ($GameDirectory) { $arguments += ' -GameDirectory "{0}"' -f $GameDirectory }
$id = [Guid]::NewGuid().ToString('N').Substring(0,8)
$child = Start-Process -FilePath $shell -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $OutputRoot ("launcher-$id.stdout.txt")) -RedirectStandardError (Join-Path $OutputRoot ("launcher-$id.stderr.txt"))
[void]$child.Handle
$deadline = [DateTime]::UtcNow.AddSeconds(15)
while ([DateTime]::UtcNow -lt $deadline) {
    if ($child.HasExited) { throw "Recorder failed. Read launcher-$id.stderr.txt in $OutputRoot." }
    $stateFile = Join-Path $OutputRoot 'active.json'
    if (Test-Path -LiteralPath $stateFile) {
        $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        if ($state.recorderPid -eq $child.Id) { Write-Output "Recorder ready: $($state.sessionDirectory)"; return }
    }
    Start-Sleep -Milliseconds 200
}
throw "Recorder did not become ready. Read launcher-$id.stderr.txt in $OutputRoot."
