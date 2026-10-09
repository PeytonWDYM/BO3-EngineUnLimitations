# Read one reviewed Windows audit bundle. This does not select an arbitrary runtime caller or target.
function Read-SoundIdentity([string]$AuditDirectory) {
    if (!$AuditDirectory) { throw 'Supply the private reviewed Windows audit directory.' }
    $identityPath = Join-Path $AuditDirectory 'identity.json'
    $identity = Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json
    $systemFile = Join-Path ([Environment]::SystemDirectory) 'DSOUND.dll'
    if (![IO.Path]::GetFullPath($identity.path).Equals($systemFile, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The audit must describe the actual System32 DirectSound module.'
    }
    if ((Get-FileHash -LiteralPath $systemFile).Hash.ToLowerInvariant() -ne $identity.sha256) {
        throw 'The audited Windows module hash has changed.'
    }
    $trace = $identity.observed_trace
    if ((Get-FileHash -LiteralPath $trace.path).Hash.ToLowerInvariant() -ne $trace.sha256 -or
        (Get-FileHash -LiteralPath $trace.run_path).Hash.ToLowerInvariant() -ne $trace.run_sha256) {
        throw 'The audited physical trace binding has changed.'
    }
    $window = $identity.call_window
    $start = [Convert]::ToUInt32($window.start_rva.Substring(2), 16)
    $end = [Convert]::ToUInt32($window.end_rva.Substring(2), 16)
    $bytes = [Convert]::FromHexString($window.hex)
    if ($bytes.Length -ne $end-$start -or $bytes.Length -gt 128 -or
        $trace.event.callerModule.rva -ne $end -or $trace.event.depth -ne 1 -or $trace.event.outer -ne 2) {
        throw 'The call-setup window does not match the measured synchronous Sound call.'
    }
    $digest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
    if ($digest -ne $window.sha256) { throw 'The audited call-setup bytes have changed.' }
    $disk = [IO.File]::ReadAllBytes($systemFile)
    $nt = [BitConverter]::ToInt32($disk, 0x3c)
    $stamp = [BitConverter]::ToUInt32($disk, $nt+8)
    $imageSize = [BitConverter]::ToUInt32($disk, $nt+24+56)
    if ($stamp -ne $identity.timestamp -or $imageSize -ne $identity.imageSize) {
        throw 'The actual Windows PE identity differs from the audit.'
    }
    # The private bundle retains the mapped-RVA window in its audited function bytes.
    $range = $identity.ranges | Where-Object {
        [Convert]::ToUInt32($_.start_rva.Substring(2),16) -le $start -and
        [Convert]::ToUInt32($_.end_rva.Substring(2),16) -ge $end
    } | Select-Object -First 1
    if (!$range) { throw 'The audit lacks the containing function range.' }
    $rangeStart = [Convert]::ToUInt32($range.start_rva.Substring(2),16)
    $rangePath = Join-Path $AuditDirectory ('range-'+$range.start_rva.Substring(2)+'.bin')
    if ((Get-FileHash -LiteralPath $rangePath).Hash.ToLowerInvariant() -ne $range.bytes_sha256) {
        throw 'The audited function bytes have changed.'
    }
    $rangeBytes = [IO.File]::ReadAllBytes($rangePath)
    for ($i=0; $i -lt $bytes.Length; $i++) {
        if ($bytes[$i] -ne $rangeBytes[$start-$rangeStart+$i]) { throw 'The call window differs from the audited function.' }
    }
    $byteText = ($bytes | ForEach-Object { '0x'+$_.ToString('x2') }) -join ','
    $escaped = $systemFile.Replace('\','\\')
    $header = @('#pragma once', "constexpr wchar_t kSoundPath[]=L`"$escaped`";",
        "constexpr char kSoundHash[]=`"$($identity.sha256)`";",
        "constexpr DWORD kSoundImageSize=$($identity.imageSize)u;", "constexpr DWORD kSoundTimestamp=$($identity.timestamp)u;",
        "constexpr DWORD kSoundCallRva=$($window.start_rva)u;", "constexpr DWORD kSoundReturnRva=$($window.end_rva)u;",
        "constexpr BYTE kSoundCallBytes[]={$byteText};") -join "`n"
    return @{header=$header; identitySha256=(Get-FileHash -LiteralPath $identityPath).Hash.ToLowerInvariant();
        windowsSha256=$identity.sha256; callWindowSha256=$window.sha256; auditDirectory=$AuditDirectory}
}
