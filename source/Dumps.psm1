Set-StrictMode -Version Latest

function Start-ProcessDump {
    param([string]$Tool, [int]$TargetId, [string]$Session)
    $path = Join-Path $Session ('snapshot-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.dmp')
    $arguments = '-accepteula -r -ma {0} "{1}"' -f $TargetId, $path
    $process = Start-Process -FilePath $Tool -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput ($path + '.stdout.txt') -RedirectStandardError ($path + '.stderr.txt')
    # Retain the handle so Windows PowerShell can read ExitCode after exit.
    [void]$process.Handle
    return [PSCustomObject]@{ Process = $process; Path = $path }
}

# Check the full memory stream, since ProcDump can return 1 after a successful snapshot.
function Complete-ProcessDump {
    param($Job)
    $Job.Process.WaitForExit()
    $result = @{ path = $Job.Path; exitCode = $Job.Process.ExitCode; complete = $false }
    try {
        $output = Get-Content -LiteralPath ($Job.Path + '.stdout.txt') -Raw -Encoding Unicode
        if ($output -notmatch 'Dump \d+ complete:' -or -not (Test-Path -LiteralPath $Job.Path)) { return $result }
        $reader = [IO.BinaryReader]::new([IO.File]::OpenRead($Job.Path))
        try {
            $length = $reader.BaseStream.Length
            if ($length -lt 32 -or $reader.ReadUInt32() -ne 0x504D444D) { return $result }
            [void]$reader.ReadUInt32()
            $streams = $reader.ReadUInt32()
            $directory = $reader.ReadUInt32()
            if ($streams -eq 0 -or [long]$directory + [long]$streams * 12 -gt $length) { return $result }
            for ($index = 0; $index -lt $streams; $index++) {
                $reader.BaseStream.Position = [long]$directory + $index * 12
                $type = $reader.ReadUInt32()
                $size = $reader.ReadUInt32()
                $offset = $reader.ReadUInt32()
                if ([long]$offset + $size -gt $length) { return $result }
                if ($type -ne 9) { continue }
                $reader.BaseStream.Position = $offset
                $ranges = $reader.ReadUInt64()
                $memoryOffset = $reader.ReadUInt64()
                if ($ranges -gt ($length / 16) -or 16 + $ranges * 16 -gt $size) { return $result }
                $memoryBytes = [uint64]0
                for ($range = 0; $range -lt $ranges; $range++) {
                    [void]$reader.ReadUInt64()
                    $memoryBytes += $reader.ReadUInt64()
                }
                if ($memoryOffset + $memoryBytes -le $length -and $memoryBytes -gt 0) {
                    $result.complete = $true
                    $result.memoryBytes = $memoryBytes
                    $result.fileBytes = $length
                }
            }
        } finally { $reader.Dispose() }
    } catch { $result.error = $_.ToString() }
    finally { $Job.Process.Dispose() }
    return $result
}

Export-ModuleMember -Function Start-ProcessDump,Complete-ProcessDump
