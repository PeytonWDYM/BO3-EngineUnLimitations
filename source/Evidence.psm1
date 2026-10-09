Set-StrictMode -Version Latest

# Save identity and loaded modules without changing the target process.
function Save-ProcessIdentity {
    param([Diagnostics.Process]$Process, [string]$Session)
    $executable = $Process.MainModule.FileName
    [ordered]@{
        pid = $Process.Id
        name = $Process.ProcessName
        executable = $executable
        sha256 = (Get-FileHash -LiteralPath $executable).Hash
        fileVersion = $Process.MainModule.FileVersionInfo.FileVersion
        startedUtc = $Process.StartTime.ToUniversalTime().ToString('o')
        modules = @($Process.Modules | ForEach-Object { @{ name = $_.ModuleName; path = $_.FileName; baseAddress = ('0x{0:X}' -f $_.BaseAddress.ToInt64()); size = $_.ModuleMemorySize } })
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Session 'process.json') -Encoding UTF8
}

# Snapshot optional external files. Missing files mean that this build does not provide them.
function Save-GameFiles {
    param([string]$GameDirectory, [string]$Session, [DateTime]$StartedUtc, [switch]$IncludeSettings)
    if (-not $GameDirectory) { return }
    $evidence = Join-Path $Session 'game-files'
    New-Item -ItemType Directory -Path $evidence -Force | Out-Null
    if ($IncludeSettings) {
        $players = Join-Path $GameDirectory 'players'
        if (Test-Path -LiteralPath $players) {
            foreach ($file in Get-ChildItem -LiteralPath $players -Filter 'aaeoption*.cfg' -File) {
                Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $evidence $file.Name)
            }
        }
    }
    # Logs can live beneath the active mod ID, in players, or beside the executable.
    $logRoots = @($GameDirectory, (Join-Path $GameDirectory 'players'), (Join-Path $GameDirectory '311210'), (Join-Path $GameDirectory 't7x'))
    foreach ($root in $logRoots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $logs = if ($root -eq $GameDirectory) { @(Get-ChildItem -LiteralPath $root -Filter '*.log' -File) } else { @(Get-ChildItem -LiteralPath $root -Filter '*.log' -File -Recurse) }
        foreach ($file in $logs) {
            if ($file.Length -gt 16MB) { continue }
            $relative = $file.FullName.Substring($GameDirectory.Length).TrimStart('\', '/')
            $destination = Join-Path $evidence $relative
            New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
            # Allow the game to keep writing its log while this snapshot is copied.
            $inputStream = [IO.File]::Open($file.FullName, 'Open', 'Read', 'ReadWrite')
            try {
                $outputStream = [IO.File]::Create($destination)
                try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
            } finally { $inputStream.Dispose() }
        }
    }
    $dumpDirectory = Join-Path $GameDirectory 'minidumps'
    if (Test-Path -LiteralPath $dumpDirectory) {
        foreach ($file in Get-ChildItem -LiteralPath $dumpDirectory -File | Where-Object { $_.LastWriteTimeUtc -ge $StartedUtc -and $_.Extension -in '.zip', '.dmp' }) {
            Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $evidence $file.Name)
        }
    }
}

# Windows events only describe process crashes or window hangs, not an internal server shutdown.
function Save-CrashEvents {
    param([string]$ProcessName, [DateTime]$StartedUtc, [string]$Session)
    $eventErrors = @()
    $events = @(Get-WinEvent -FilterHashtable @{ LogName = 'Application'; Id = 1000,1001,1002; StartTime = $StartedUtc.ToLocalTime() } -ErrorAction SilentlyContinue -ErrorVariable eventErrors)
    $unexpectedErrors = @($eventErrors | Where-Object { $_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*' })
    if ($unexpectedErrors.Count -gt 0) { throw $unexpectedErrors[0] }
    $matching = @($events | Where-Object { $_.Message -match [Regex]::Escape($ProcessName) } | ForEach-Object {
        @{ utc = $_.TimeCreated.ToUniversalTime().ToString('o'); id = $_.Id; provider = $_.ProviderName; message = $_.Message }
    })
    ConvertTo-Json -InputObject $matching -Depth 5 | Set-Content -LiteralPath (Join-Path $Session 'windows-events.json') -Encoding UTF8
}

Export-ModuleMember -Function Save-ProcessIdentity,Save-GameFiles,Save-CrashEvents
