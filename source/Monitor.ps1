[CmdletBinding()]
param(
    [string]$ProcessName = 'BlackOps3',
    [string]$OutputRoot = '',
    [string]$GameDirectory = '',
    [string]$ProcDumpPath = '',
    [ValidateRange(100,60000)][int]$SampleMilliseconds = 1000,
    [switch]$NoHotkeys
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = Split-Path $PSScriptRoot -Parent
if (-not $OutputRoot) { $OutputRoot = Join-Path $repo 'research/captures/live' }
if (-not $ProcDumpPath) { $ProcDumpPath = Join-Path $repo 'tools/procdump/procdump64.exe' }
Import-Module (Join-Path $PSScriptRoot 'Evidence.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'Dumps.psm1') -Force
if (-not $NoHotkeys) { Add-Type -Path (Join-Path $PSScriptRoot 'Hotkeys.cs') }
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
# Keep one recorder per output root, even when a previous process left stale metadata.
$lock = [IO.File]::Open((Join-Path $OutputRoot 'active.lock'), 'OpenOrCreate', 'ReadWrite', 'Read')
$session = Join-Path $OutputRoot ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8))
$requests = Join-Path $session 'requests'
New-Item -ItemType Directory -Path $requests -Force | Out-Null
$events = [IO.StreamWriter]::new((Join-Path $session 'events.jsonl'), $false, [Text.UTF8Encoding]::new($false))
$metrics = [IO.StreamWriter]::new((Join-Path $session 'metrics.csv'), $false, [Text.UTF8Encoding]::new($false))
$events.AutoFlush = $true
$metrics.AutoFlush = $true
$metrics.WriteLine('utc,elapsed_seconds,pid,cpu_percent,private_bytes,working_set_bytes,virtual_bytes,handles,threads,window_responding')
$started = [DateTime]::UtcNow
$clock = [Diagnostics.Stopwatch]::StartNew()
$target = $null
$dumpJob = $null
$stop = $false
$nextSample = 0L
$nextFiles = 0L
$previousCpu = 0.0
$previousSample = 0L
$held = @{}
$keys = @{ 0x75 = 'match-start'; 0x76 = 'fire-start'; 0x77 = 'fire-end'; 0x78 = 'connection-interrupted'; 0x79 = 'stop' }
$culture = [Globalization.CultureInfo]::InvariantCulture

function Write-Event {
    param([string]$Type, $Data = @{}, [string]$Utc = [DateTime]::UtcNow.ToString('o'))
    $events.WriteLine((@{ utc = $Utc; elapsedSeconds = [Math]::Round($clock.Elapsed.TotalSeconds,3); type = $Type; data = $Data } | ConvertTo-Json -Depth 8 -Compress))
}

try {
    Write-Event 'recorder_started' @{ processName = $ProcessName; sampleMilliseconds = $SampleMilliseconds; hotkeys = (-not $NoHotkeys); entityCounters = 'unavailable'; dumpMode = 'manual full snapshot' }
    Write-Event 'waiting_for_process'
    $stateTemporary = Join-Path $OutputRoot 'active.tmp'
    [ordered]@{ recorderPid = $PID; recorderStartedUtc = (Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o'); sessionDirectory = $session; startedUtc = $started.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $stateTemporary -Encoding UTF8
    Move-Item -LiteralPath $stateTemporary -Destination (Join-Path $OutputRoot 'active.json') -Force
    Write-Output "Recording: $session"
    while (-not $stop) {
        if ($null -eq $target -and $clock.ElapsedMilliseconds -ge $nextSample) {
            $candidates = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
            if ($candidates.Count -gt 1) { throw "More than one $ProcessName process is running. Close the extra process." }
            if ($candidates.Count -eq 1) {
                $target = $candidates[0]
                $previousCpu = $target.TotalProcessorTime.TotalMilliseconds
                $previousSample = $clock.ElapsedMilliseconds
                Write-Event 'process_attached' @{ pid = $target.Id; name = $target.ProcessName }
                try { Save-ProcessIdentity -Process $target -Session $session } catch { Write-Event 'evidence_error' @{ operation = 'process identity'; message = $_.ToString() } }
                if (-not $GameDirectory -and $ProcessName -eq 'BlackOps3') { $GameDirectory = Split-Path $target.MainModule.FileName -Parent }
                try { Save-GameFiles -GameDirectory $GameDirectory -Session $session -StartedUtc $started -IncludeSettings } catch { Write-Event 'evidence_error' @{ operation = 'game files'; message = $_.ToString() } }
            }
            $nextSample = $clock.ElapsedMilliseconds + $SampleMilliseconds
        }
        if ($null -ne $target) {
            $target.Refresh()
            if ($target.HasExited) { Write-Event 'process_exited' @{ pid = $target.Id }; break }
            if ($clock.ElapsedMilliseconds -ge $nextSample) {
                # A process can exit between Refresh and reading its counters.
                try {
                    $now = $clock.ElapsedMilliseconds
                    $cpu = $target.TotalProcessorTime.TotalMilliseconds
                    $cpuPercent = [Math]::Round(100 * ($cpu - $previousCpu) / [Math]::Max(1,($now - $previousSample)) / [Environment]::ProcessorCount,2)
                    $fields = @([DateTime]::UtcNow.ToString('o'), $clock.Elapsed.TotalSeconds.ToString('F3',$culture), $target.Id, $cpuPercent.ToString($culture), $target.PrivateMemorySize64, $target.WorkingSet64, $target.VirtualMemorySize64, $target.HandleCount, $target.Threads.Count, $target.Responding)
                    $metrics.WriteLine(($fields -join ','))
                    $previousCpu = $cpu
                    $previousSample = $now
                } catch {
                    $target.Refresh()
                    if ($target.HasExited) { Write-Event 'process_exited' @{ pid = $target.Id }; break }
                    throw
                }
                $nextSample = $clock.ElapsedMilliseconds + $SampleMilliseconds
            }
            if ($clock.ElapsedMilliseconds -ge $nextFiles) {
                try { Save-GameFiles -GameDirectory $GameDirectory -Session $session -StartedUtc $started } catch { Write-Event 'evidence_error' @{ operation = 'game files'; message = $_.ToString() } }
                $nextFiles = $clock.ElapsedMilliseconds + 10000
            }
        }
        if ($null -ne $dumpJob -and $dumpJob.Process.HasExited) {
            $result = Complete-ProcessDump -Job $dumpJob
            $type = if ($result.complete) { 'dump_completed' } else { 'dump_failed' }
            Write-Event $type $result
            $dumpJob = $null
        }
        $pending = [Collections.Generic.List[object]]::new()
        if (-not $NoHotkeys) {
            foreach ($key in $keys.Keys) {
                $down = [RecorderHotkeys]::IsDown($key)
                if ($down -and -not $held[$key]) { $pending.Add(@{ action = $keys[$key]; utc = [DateTime]::UtcNow.ToString('o'); data = @{ source = 'hotkey' } }) }
                $held[$key] = $down
            }
        }
        foreach ($file in Get-ChildItem -LiteralPath $requests -Filter '*.json' -File | Sort-Object CreationTimeUtc) {
            $pending.Add((Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json))
            Remove-Item -LiteralPath $file.FullName
        }
        foreach ($request in $pending) {
            Write-Event $request.action $request.data $request.utc
            if ($request.action -eq 'stop') { $stop = $true }
            if ($request.action -in 'connection-interrupted','dump') {
                if ($null -eq $target) { Write-Event 'dump_skipped' @{ reason = 'No target process.' }; continue }
                if ($null -ne $dumpJob) { Write-Event 'dump_skipped' @{ reason = 'A dump is already in progress.' }; continue }
                try {
                    # PSS cloning reduces the time the game pauses. Never terminate the game.
                    $dumpJob = Start-ProcessDump -Tool $ProcDumpPath -TargetId $target.Id -Session $session
                    Write-Event 'dump_started' @{ path = $dumpJob.Path; pid = $target.Id; toolPid = $dumpJob.Process.Id }
                } catch { Write-Event 'dump_failed' @{ message = $_.ToString() } }
            }
        }
        Start-Sleep -Milliseconds 100
    }
} catch {
    Write-Event 'recorder_error' @{ message = $_.ToString() }
    throw
} finally {
    if ($null -ne $dumpJob) {
        # Allow an already requested dump to finish. The recorder does not start another capture here.
        $result = Complete-ProcessDump -Job $dumpJob
        $type = if ($result.complete) { 'dump_completed' } else { 'dump_failed' }
        Write-Event $type $result
    }
    try { Save-GameFiles -GameDirectory $GameDirectory -Session $session -StartedUtc $started -IncludeSettings } catch { Write-Event 'evidence_error' @{ operation = 'final game files'; message = $_.ToString() } }
    try { Save-CrashEvents -ProcessName $ProcessName -StartedUtc $started -Session $session } catch { Write-Event 'evidence_error' @{ operation = 'Windows events'; message = $_.ToString() } }
    Write-Event 'recorder_stopped'
    $metrics.Dispose()
    $events.Dispose()
    $lock.Dispose()
    if ($null -ne $target) { $target.Dispose() }
}
