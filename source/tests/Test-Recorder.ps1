[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$artifact = Join-Path $repo ('research/captures/e2e/' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $artifact -Force | Out-Null
$shell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$monitorScript = Join-Path $repo 'source/Monitor.ps1'
$markerScript = Join-Path $repo 'source/Send-Marker.ps1'
$fixtureName = 'RecorderFixture' + [Guid]::NewGuid().ToString('N')
$fixtureExe = Join-Path $artifact ($fixtureName + '.exe')
$gameFixture = Join-Path $artifact 'game-files'
New-Item -ItemType Directory -Path (Join-Path $gameFixture 'players') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $gameFixture '311210/2631943123') -Force | Out-Null
'E2E console evidence' | Set-Content -LiteralPath (Join-Path $gameFixture '311210/2631943123/console_mp.log')
'E2E AAE settings' | Set-Content -LiteralPath (Join-Path $gameFixture 'players/aaeoption.cfg')
Add-Type -TypeDefinition 'public class RecorderFixture { public static void Main() { System.Threading.Thread.Sleep(120000); } }' -OutputAssembly $fixtureExe -OutputType ConsoleApplication
$checks = [Collections.Generic.List[string]]::new()
$owned = [Collections.Generic.List[Diagnostics.Process]]::new()

# Wait for an observable artifact, with a deadline that fails the test.
function Wait-For {
    param([scriptblock]$Condition, [string]$Description, [int]$Seconds = 20)
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (& $Condition) { return }
        Start-Sleep -Milliseconds 100
    }
    throw "Timed out: $Description"
}

function Start-TestRecorder {
    param([string]$Root, [string]$ProcDump)
    New-Item -ItemType Directory -Path $Root -Force | Out-Null
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -ProcessName "{1}" -OutputRoot "{2}" -ProcDumpPath "{3}" -GameDirectory "{4}" -SampleMilliseconds 200 -NoHotkeys' -f $monitorScript, $fixtureName, $Root, $ProcDump, $gameFixture
    $recorder = Start-Process -FilePath $shell -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Root 'stdout.txt') -RedirectStandardError (Join-Path $Root 'stderr.txt')
    [void]$recorder.Handle
    $owned.Add($recorder)
    Wait-For { Test-Path -LiteralPath (Join-Path $Root 'active.json') } 'recorder ready'
    $state = Get-Content -LiteralPath (Join-Path $Root 'active.json') -Raw | ConvertFrom-Json
    return [PSCustomObject]@{ Process = $recorder; Session = $state.sessionDirectory; Root = $Root }
}

function Read-Events {
    param([string]$Session)
    Get-Content -LiteralPath (Join-Path $Session 'events.jsonl') | ForEach-Object { $_ | ConvertFrom-Json }
}

try {
    $run = Start-TestRecorder (Join-Path $artifact 'manual') (Join-Path $repo 'tools/procdump/procdump64.exe')
    Wait-For { @(Read-Events $run.Session | Where-Object type -eq 'waiting_for_process').Count -eq 1 } 'waiting event'
    $checks.Add('Waits for the target and flushes its waiting event.')

    $powerShell7 = (Get-Command pwsh -ErrorAction Stop).Source
    & $powerShell7 -NoProfile -File $markerScript -OutputRoot $run.Root -Action note -Note 'PowerShell 7 marker'
    if ($LASTEXITCODE -ne 0) { throw 'PowerShell 7 rejected a valid recorder identity.' }
    Wait-For { @(Read-Events $run.Session | Where-Object { $_.type -eq 'note' -and $_.data.note -eq 'PowerShell 7 marker' }).Count -eq 1 } 'PowerShell 7 marker'
    $checks.Add('Accepts markers from PowerShell 7 with decoded JSON timestamps.')

    $duplicate = Start-Process -FilePath $shell -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -ProcessName "{1}" -OutputRoot "{2}" -NoHotkeys' -f $monitorScript, $fixtureName, $run.Root) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifact 'duplicate.stdout.txt') -RedirectStandardError (Join-Path $artifact 'duplicate.stderr.txt')
    [void]$duplicate.Handle
    $owned.Add($duplicate)
    Wait-For { $duplicate.HasExited } 'duplicate rejected'
    if ($duplicate.ExitCode -eq 0 -or $run.Process.HasExited) { throw 'Duplicate recording was not rejected safely.' }
    $checks.Add('Rejects a duplicate recorder without disturbing the first recorder.')

    $target = Start-Process -FilePath $fixtureExe -WindowStyle Hidden -PassThru
    $owned.Add($target)
    Wait-For { @(Import-Csv -LiteralPath (Join-Path $run.Session 'metrics.csv')).Count -ge 3 } 'live telemetry'
    $copiedLog = Join-Path $run.Session 'game-files/311210/2631943123/console_mp.log'
    $copiedSettings = Join-Path $run.Session 'game-files/aaeoption.cfg'
    if ((Get-Content -LiteralPath $copiedLog -Raw) -notmatch 'E2E console evidence' -or (Get-Content -LiteralPath $copiedSettings -Raw) -notmatch 'E2E AAE settings') { throw 'Game evidence was not copied.' }
    if ((Get-FileHash -LiteralPath $copiedLog).Hash -ne (Get-FileHash -LiteralPath (Join-Path $gameFixture '311210/2631943123/console_mp.log')).Hash) { throw 'The source log changed.' }
    $checks.Add('Copies game logs and AAE settings while preserving the originals.')
    & $markerScript -OutputRoot $run.Root -Action match-start -Mode Coop -PlayerCount 3 -HostRole Host -Map 'E2E map' -Round 40
    & $markerScript -OutputRoot $run.Root -Action fire-start -Note 'Upgraded War Machine volley'
    & $markerScript -OutputRoot $run.Root -Action connection-interrupted -Round 41
    Wait-For { @(Read-Events $run.Session | Where-Object type -eq 'dump_completed').Count -eq 1 } 'snapshot dump' 45
    $dumpEvent = Read-Events $run.Session | Where-Object type -eq 'dump_completed' | Select-Object -Last 1
    if (-not $dumpEvent.data.complete) { throw 'The full memory snapshot is incomplete.' }
    $dumpStream = [IO.File]::OpenRead($dumpEvent.data.path)
    try {
        $signature = New-Object byte[] 4
        [void]$dumpStream.Read($signature, 0, 4)
        if ([Text.Encoding]::ASCII.GetString($signature) -ne 'MDMP') { throw 'Dump signature is invalid.' }
    } finally { $dumpStream.Dispose() }
    $before = @(Import-Csv -LiteralPath (Join-Path $run.Session 'metrics.csv')).Count
    Wait-For { @(Import-Csv -LiteralPath (Join-Path $run.Session 'metrics.csv')).Count -gt $before } 'telemetry after dump'
    if ($target.HasExited) { throw 'The dump terminated the target.' }
    $checks.Add('Captures a valid dump while the target stays alive and telemetry continues.')

    $match = Read-Events $run.Session | Where-Object type -eq 'match-start'
    $fire = Read-Events $run.Session | Where-Object type -eq 'fire-start'
    if ($match.data.map -ne 'E2E map' -or $match.data.playerCount -ne 3 -or $match.data.hostRole -ne 'Host' -or $fire.data.note -ne 'Upgraded War Machine volley') { throw 'Marker context was lost.' }
    $checks.Add('Preserves match context and firing markers.')

    & $markerScript -OutputRoot $run.Root -Action stop
    Wait-For { $run.Process.HasExited } 'clean stop'
    if ($run.Process.ExitCode -ne 0 -or $target.HasExited) { throw 'Stop failed or terminated the target.' }
    if ((Read-Events $run.Session | Select-Object -Last 1).type -ne 'recorder_stopped') { throw 'Final event was not flushed.' }
    $checks.Add('Stops cleanly and leaves the target alive.')

    $run = Start-TestRecorder (Join-Path $artifact 'failed-dump') (Join-Path $env:SystemRoot 'System32/whoami.exe')
    Wait-For { @(Import-Csv -LiteralPath (Join-Path $run.Session 'metrics.csv')).Count -ge 2 } 'second capture attached'
    & $markerScript -OutputRoot $run.Root -Action connection-interrupted
    Wait-For { @(Read-Events $run.Session | Where-Object type -eq 'dump_failed').Count -eq 1 } 'tool failure recorded'
    $before = @(Import-Csv -LiteralPath (Join-Path $run.Session 'metrics.csv')).Count
    Wait-For { @(Import-Csv -LiteralPath (Join-Path $run.Session 'metrics.csv')).Count -gt $before } 'telemetry after tool failure'
    $checks.Add('Records a dump failure and continues sampling.')
    $target.Kill()
    Wait-For { $run.Process.HasExited } 'process exit saved'
    if ($run.Process.ExitCode -ne 0 -or @(Read-Events $run.Session | Where-Object type -eq 'process_exited').Count -ne 1) { throw 'Target exit was not recorded.' }
    $checks.Add('Saves target exit and closes the session.')

    [PSCustomObject]@{ passed = $true; completedUtc = [DateTime]::UtcNow.ToString('o'); checks = $checks.ToArray(); artifact = $artifact } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $artifact 'report.json') -Encoding UTF8
    Write-Output "PASS: $artifact"
} catch {
    [PSCustomObject]@{ passed = $false; error = $_.ToString(); checks = $checks.ToArray(); artifact = $artifact } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $artifact 'report.json') -Encoding UTF8
    throw
} finally {
    foreach ($child in $owned) { if (-not $child.HasExited) { $child.Kill() } }
}
