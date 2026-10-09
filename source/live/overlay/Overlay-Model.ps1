function Get-OverlayModel {
    param([Parameter(Mandatory)][object]$State, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    $age = if ($State.lastSampleUtc) { [Math]::Max(0, ($Now - [datetimeoffset]::Parse($State.lastSampleUtc)).TotalSeconds) } else { $null }
    $status = if ($State.event -in @('stopped', 'process-exited', 'interrupted')) { 'STOPPED' }
        elseif ($null -ne $age -and $age -ge 5) { 'STALE' }
        elseif ($State.event -eq 'rejected') { 'READ REJECTED' }
        elseif ($null -eq $age) { 'WAITING' }
        else { 'LIVE READ' }
    $lines = [Collections.Generic.List[string]]::new()
    $lines.Add("BO3 diagnostics | $status")
    $lines.Add('External read-only monitor | 1 Hz')
    $server = @($State.lastSample) | Where-Object index -eq 0 | Select-Object -First 1
    if ($server -and $server.status -eq 'initialized') {
        $lines.Add(('Server slots : {0:N0} / {1:N0}' -f $server.allocated, $server.usableCapacity))
        $lines.Add(('Free slots   : {0:N0}' -f $server.free))
        $lines.Add(('Cleanup queue: {0:N0}' -f $server.deferredCount))
        $lines.Add(('Call depth   : {0:N0}' -f $server.currentFunctionDepth))
        $lines.Add(('First error  : {0}' -f $server.firstError.text))
    } else { $lines.Add('Server pool  : no accepted initialized sample') }
    $ageText = if ($null -eq $age) { 'none' } else { '{0:N1}s' -f $age }
    $lines.Add("Sample age   : $ageText")
    $lines.Add(('Reads        : {0} accepted / {1} rejected' -f $State.accepted, $State.rejected))
    $lines.Add(('Read duration: {0} ms' -f $State.readMilliseconds))
    $lines.Add('Moving-match rows remain provisional.')
    $lines.Add('Tray icon: hide/show or exit overlay')
    [pscustomobject]@{ Text = $lines -join "`r`n"; Status = $status; Exhausted = ($server -and $server.free -eq 0) }
}
