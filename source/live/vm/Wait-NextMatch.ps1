#Requires -Version 7.0
param([Parameter(Mandatory)][string]$ProfileTemplate, [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo = PhysicalPath (Join-Path $PSScriptRoot '../../..')
$output = PhysicalPath $OutputDirectory
if ($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep monitoring evidence outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Use a new monitor output directory.' }
New-Item -ItemType Directory -Path $output | Out-Null
$waiting = Join-Path $output 'waiting.json'
@{event='waiting';lastSample=$null;lastSampleUtc=$null;accepted=0;rejected=0;readMilliseconds=0} |
    ConvertTo-Json | Set-Content -LiteralPath $waiting -Encoding utf8
$overlayScript = Join-Path $PSScriptRoot '../overlay/Show-Diagnostics.ps1'
$shell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
function StartOverlay([string]$Latest, [string]$Name) {
    $arguments = '-NoProfile -STA -File "{0}" -Latest "{1}"' -f $overlayScript,$Latest
    $previousModulePath = $env:PSModulePath
    try {
        $env:PSModulePath = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/Modules'
        return Start-Process -FilePath $shell -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput "$output/$Name.stdout.txt" -RedirectStandardError "$output/$Name.stderr.txt"
    } finally { $env:PSModulePath = $previousModulePath }
}
$waitingOverlay = StartOverlay $waiting 'waiting-overlay'
$monitor = $null
$overlay = $null
$handoff = $false
try {
    while ($true) {
        $games = @(Get-Process -Name BlackOps3 -ErrorAction SilentlyContinue)
        if ($games.Count -gt 1) { throw 'Multiple BO3 processes. No monitor attached.' }
        if ($games.Count -eq 1) {
            $game = $games[0]
            $native = @($game.Modules | Where-Object { $_.ModuleName -eq 'T7Overcharged.ff' -and $_.FileName -like '*\2631943123\*' })
            if ($native.Count -eq 1) { break }
        }
        Start-Sleep -Seconds 1
    }
    $profile = Get-Content -LiteralPath $ProfileTemplate -Raw | ConvertFrom-Json
    $ticks = $game.StartTime.ToUniversalTime().ToFileTimeUtc()
    $profile | Add-Member -NotePropertyName expectedProcessStartTicks -NotePropertyValue $ticks -Force
    $bound = Join-Path $output 'bound-profile.json'
    $profile | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $bound -Encoding utf8
    $latest = Join-Path $output 'latest.json'
    $sampler = Join-Path $PSScriptRoot 'Read-LiveVm.py'
    $arguments = '"{0}" --pid {1} --profile "{2}" --output "{3}" --latest "{4}" --rate 1 --duration 0 --attempts 1 --expected-start-ticks {5}' -f $sampler,$game.Id,$bound,"$output/rows.jsonl",$latest,$ticks
    $monitor = Start-Process -FilePath $Python -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput "$output/monitor.stdout.txt" -RedirectStandardError "$output/monitor.stderr.txt"
    $deadline = [datetime]::UtcNow.AddSeconds(20)
    while (!(Test-Path -LiteralPath $latest)) {
        if ($monitor.HasExited -or [datetime]::UtcNow -gt $deadline) { throw 'Sampler refused attachment. Read monitor.stderr.txt. No game state changed.' }
        Start-Sleep -Milliseconds 200
    }
    if (!$waitingOverlay.HasExited) { Stop-Process -InputObject $waitingOverlay -Force }
    $overlay = StartOverlay $latest 'live-overlay'
    @{gamePid=$game.Id;processStartTicks=$ticks;monitorPid=$monitor.Id;overlayPid=$overlay.Id;
        scope='External read-only samples. Moving-match rows remain provisional. Capacity requires runtime enrollment.'} |
        ConvertTo-Json | Set-Content -LiteralPath "$output/attached.json" -Encoding utf8
    $handoff = $true
} finally {
    if (!$waitingOverlay.HasExited) { Stop-Process -InputObject $waitingOverlay -Force }
    if (!$handoff) {
        foreach ($owned in @($monitor,$overlay)) {
            if ($null -ne $owned -and !$owned.HasExited) { Stop-Process -InputObject $owned -Force -ErrorAction SilentlyContinue }
        }
    }
}
