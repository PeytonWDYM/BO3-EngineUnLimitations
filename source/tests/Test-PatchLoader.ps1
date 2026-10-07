[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)

$ErrorActionPreference = 'Stop'
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
& (Join-Path $PSScriptRoot '../loader/Build-PatchLoader.ps1') -OutputDirectory (Join-Path $OutputDirectory 'bin') -IncludeE2EFaultFixture
$fixturePath = Join-Path $OutputDirectory 'bin/PatchLoaderFixture.exe'
$loaderPath = Join-Path $OutputDirectory 'bin/PatchLoader.exe'
$originalHash = (Get-FileHash -LiteralPath $fixturePath -Algorithm SHA256).Hash.ToLowerInvariant()
$cases = [Collections.Generic.List[object]]::new()
$processes = [Collections.Generic.List[Diagnostics.Process]]::new()

function Start-Fixture([string]$Name, [string]$Mode = '') {
    $stdout = Join-Path $OutputDirectory "$Name-fixture.log"
    $stderr = Join-Path $OutputDirectory "$Name-fixture-error.log"
    $arguments = if ($Mode) { @($Mode) } else { @('--normal') }
    $process = Start-Process -FilePath $fixturePath -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $processes.Add($process)
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 50
        $lines = if (Test-Path -LiteralPath $stdout) { @(Get-Content -LiteralPath $stdout) } else { @() }
        if ($process.HasExited) { throw "Fixture exited: $Name" }
    } while ((-not ($lines | Where-Object { $_ -like 'READY *' })) -and [DateTime]::UtcNow -lt $deadline)
    $ready = $lines | Where-Object { $_ -like 'READY *' } | Select-Object -First 1
    if (-not $ready) { throw "Fixture did not become ready: $Name" }
    $fields = @{}
    foreach ($part in $ready.Split(' ') | Select-Object -Skip 1) {
        $pair = $part.Split('=', 2)
        $fields[$pair[0]] = $pair[1]
    }
    [pscustomobject]@{ Process=$process; Fields=$fields; Log=$stdout }
}

function Write-Profile([string]$Name, $Fixture, [string[]]$Records) {
    $path = Join-Path $OutputDirectory "$Name.profile"
    $text = @(
        'BO3_RUNTIME_PATCH_PROFILE 1'
        'id fixture-v1'
        "target $fixturePath"
        "sha256 $originalHash"
        "image_size $($Fixture.Fields.image_size)"
        "timestamp $($Fixture.Fields.timestamp)"
        'safety fixture-cooperative-v2'
    ) + $Records
    [IO.File]::WriteAllLines($path, $text, [Text.UTF8Encoding]::new($false))
    return $path
}

function Invoke-Case([string]$Name, [string]$Command, [string]$Profile, $Fixture, [int]$ExpectedExit = 1, [string]$ExpectedMessage = '', [string]$Tool = $loaderPath) {
    $output = @(& $Tool $Command --profile $Profile --pid $Fixture.Process.Id --hold-ms 800 2>&1)
    $exitCode = $LASTEXITCODE
    $log = $output -join "`n"
    [IO.File]::WriteAllText((Join-Path $OutputDirectory "$Name-loader.log"), $log)
    if ($exitCode -ne $ExpectedExit) { throw "${Name}: exit $exitCode, expected $ExpectedExit. $log" }
    if ($ExpectedMessage -and -not $log.Contains($ExpectedMessage)) { throw "${Name}: missing message $ExpectedMessage. $log" }
    $cases.Add([pscustomobject]@{ name=$Name; exit_code=$exitCode; expected_exit=$ExpectedExit; passed=$true; output=$log })
}

try {
    $normal = Start-Fixture 'normal'
    $data = "patch $($normal.Fields.data_rva) 29000000 2a000000"
    $code = "patch $($normal.Fields.code_rva) 29000000 2a000000"
    $profile = Write-Profile 'normal' $normal @($data, $code)
    Invoke-Case 'inspect' 'inspect' $profile $normal 0 'verified'
    Invoke-Case 'session' 'session' $profile $normal 0 'removed'
    Start-Sleep -Milliseconds 100
    $normalOutput = Get-Content -LiteralPath $normal.Log -Raw
    if (-not $normalOutput.Contains('VALUE data=42 code=42')) { throw 'Fixture never observed both replacements.' }
    if ([regex]::Matches($normalOutput, 'VALUE data=41 code=41').Count -lt 2) { throw 'Fixture did not return to original behavior.' }
    $protections = @([regex]::Matches($normalOutput, 'VALUE data=\d+ code=\d+ data_protect=(\d+) code_protect=(\d+)') | ForEach-Object { "$($_.Groups[1].Value),$($_.Groups[2].Value)" } | Select-Object -Unique)
    if ($protections.Count -ne 1) { throw 'Fixture page protection changed across application or removal.' }
    Invoke-Case 'inspect-restored' 'inspect' $profile $normal 0 'verified'

    $failureProfiles = @(
        @{ name='wrong-hash'; replacement=('sha256 ' + ('0' * 64)); pattern='^sha256 .+$'; message='SHA256' },
        @{ name='wrong-path'; replacement=('target ' + (Join-Path $OutputDirectory 'other.exe')); pattern='^target .+$'; message='path' },
        @{ name='wrong-size'; replacement='image_size 2147483647'; pattern='^image_size .+$'; message='image size' },
        @{ name='wrong-timestamp'; replacement='timestamp 0'; pattern='^timestamp .+$'; message='timestamp' },
        @{ name='outside-image'; replacement='patch 0xffffffffffffffff 29 2a'; pattern='^patch .+$'; message='image bounds' },
        @{ name='wrong-bytes'; replacement="patch $($normal.Fields.data_rva) 28000000 2a000000"; pattern='^patch .+$'; message='original bytes' },
        @{ name='bad-hex'; replacement="patch $($normal.Fields.data_rva) zz000000 2a000000"; pattern='^patch .+$'; message='hex' },
        @{ name='unequal-bytes'; replacement="patch $($normal.Fields.data_rva) 2900 2a"; pattern='^patch .+$'; message='length' },
        @{ name='wrong-safety'; replacement='safety unsupported'; pattern='^safety .+$'; message='safe-point contract' }
    )
    foreach ($case in $failureProfiles) {
        $casePath = Join-Path $OutputDirectory "$($case.name).profile"
        $changed = (Get-Content -LiteralPath $profile) -replace $case.pattern, $case.replacement
        # Use one record for malformed-record cases so overlap cannot hide the intended error.
        if ($case.pattern -eq '^patch .+$') { $changed = @($changed | Where-Object { $_ -notlike 'patch *' }) + $case.replacement }
        [IO.File]::WriteAllLines($casePath, $changed)
        $command = if ($case.name -eq 'wrong-safety') { 'session' } else { 'inspect' }
        Invoke-Case $case.name $command $casePath $normal 1 $case.message
    }
    $overlap = Write-Profile 'overlap' $normal @($data, $data)
    Invoke-Case 'overlap' 'inspect' $overlap $normal 1 'overlap'
    $duplicate = Join-Path $OutputDirectory 'duplicate.profile'
    [IO.File]::WriteAllLines($duplicate, @((Get-Content -LiteralPath $profile)) + 'id duplicate')
    Invoke-Case 'duplicate' 'inspect' $duplicate $normal 1 'duplicate'
    $unknown = Join-Path $OutputDirectory 'unknown-field.profile'
    [IO.File]::WriteAllLines($unknown, @((Get-Content -LiteralPath $profile)) + 'unknown field')
    Invoke-Case 'unknown-field' 'inspect' $unknown $normal 1 'Unknown profile field'
    $tooMany = Write-Profile 'too-many-records' $normal (@($data) * 129)
    Invoke-Case 'too-many-records' 'inspect' $tooMany $normal 1 'record limits'
    $oversized = Write-Profile 'oversized-record' $normal @("patch $($normal.Fields.data_rva) $('29' * 4097) $('2a' * 4097)")
    Invoke-Case 'oversized-record' 'inspect' $oversized $normal 1 'hex byte length'

    $denied = Start-Fixture 'rollback'
    $rollbackProfile = Write-Profile 'rollback' $denied @("patch $($denied.Fields.data_rva) 29000000 2a000000", "patch $($denied.Fields.code_rva) 29000000 2a000000")
    Invoke-Case 'rollback' 'session' $rollbackProfile $denied 1 'rollback complete' (Join-Path $OutputDirectory 'bin/PatchLoaderRollbackFixture.exe')
    Invoke-Case 'rollback-restored' 'inspect' $rollbackProfile $denied 0 'verified'

    $delayed = Start-Fixture 'timeout-retry' '--delay-first-safe-point'
    $delayedProfile = Write-Profile 'timeout-retry' $delayed @("patch $($delayed.Fields.data_rva) 29000000 2a000000", "patch $($delayed.Fields.code_rva) 29000000 2a000000")
    Invoke-Case 'delayed-timeout' 'session' $delayedProfile $delayed 1 'safe-point timeout'
    Invoke-Case 'delayed-retry' 'session' $delayedProfile $delayed 0 'removed' (Join-Path $OutputDirectory 'bin/PatchLoaderSafePointFixture.exe')
    Start-Sleep -Milliseconds 100
    $delayedOutput = Get-Content -LiteralPath $delayed.Log -Raw
    if ($delayedOutput.Contains('VALUE data=42 code=41') -or $delayedOutput.Contains('VALUE data=41 code=42')) {
        throw 'The retry let the fixture execute between patch records.'
    }
    if (-not $delayedOutput.Contains('VALUE data=42 code=42')) { throw 'The retry did not apply both records.' }
    if ([regex]::Matches($delayedOutput, 'VALUE data=41 code=41').Count -lt 2) { throw 'The retry did not restore both records.' }

    $exclusive = Start-Fixture 'session-owner'
    $exclusiveProfile = Write-Profile 'session-owner' $exclusive @("patch $($exclusive.Fields.data_rva) 29000000 2a000000", "patch $($exclusive.Fields.code_rva) 29000000 2a000000")
    $startInfo = [Diagnostics.ProcessStartInfo]::new($loaderPath)
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in @('session', '--profile', $exclusiveProfile, '--pid', "$($exclusive.Process.Id)", '--hold-ms', '3000')) {
        $startInfo.ArgumentList.Add($argument)
    }
    $owner = [Diagnostics.Process]::Start($startInfo)
    $processes.Add($owner)
    $ownerDeadline = [DateTime]::UtcNow.AddSeconds(5)
    do {
        Start-Sleep -Milliseconds 20
        $ownerFixtureOutput = Get-Content -LiteralPath $exclusive.Log -Raw
    } while (-not $ownerFixtureOutput.Contains('VALUE data=42 code=42') -and [DateTime]::UtcNow -lt $ownerDeadline)
    if (-not $ownerFixtureOutput.Contains('VALUE data=42 code=42')) { throw 'The first loader did not acquire its session.' }
    Invoke-Case 'concurrent-session' 'session' $exclusiveProfile $exclusive 1 'already owns'
    if (-not $owner.WaitForExit(10000)) { throw 'The first loader did not finish its session.' }
    $ownerOutput = $owner.StandardOutput.ReadToEnd() + $owner.StandardError.ReadToEnd()
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'session-owner-loader.log'), $ownerOutput)
    if ($owner.ExitCode -ne 0 -or -not $ownerOutput.Contains('removed')) { throw "Concurrent rejection interrupted the owner: $ownerOutput" }
    $cases.Add([pscustomobject]@{ name='session-owner'; exit_code=$owner.ExitCode; expected_exit=0; passed=$true; output=$ownerOutput })

    foreach ($mode in @('--no-events', '--ignore-safe-point')) {
        $name = $mode.TrimStart('-')
        $fixture = Start-Fixture $name $mode
        $safeProfile = Write-Profile $name $fixture @("patch $($fixture.Fields.data_rva) 29000000 2a000000")
        $message = if ($mode -eq '--no-events') { 'safe-point contract' } else { 'safe-point timeout' }
        Invoke-Case $name 'session' $safeProfile $fixture 1 $message
        Invoke-Case "$name-unchanged" 'inspect' $safeProfile $fixture 0 'verified'
    }
    $exit = Start-Fixture 'exit-after-apply' '--exit-after-resume'
    $exitProfile = Write-Profile 'exit-after-apply' $exit @("patch $($exit.Fields.data_rva) 29000000 2a000000")
    Invoke-Case 'exit-after-apply' 'session' $exitProfile $exit 0 'Runtime patch no longer exists'

    $conflict = Start-Fixture 'conflict' '--mutate-after-resume'
    $conflictProfile = Write-Profile 'conflict' $conflict @("patch $($conflict.Fields.data_rva) 29000000 2a000000", "patch $($conflict.Fields.code_rva) 29000000 2a000000")
    Invoke-Case 'removal-conflict' 'session' $conflictProfile $conflict 1 'removal conflict'
    Start-Sleep -Milliseconds 100
    $conflictOutput = Get-Content -LiteralPath $conflict.Log -Raw
    if (-not $conflictOutput.Contains('VALUE data=99 code=42')) { throw 'Removal overwrote the fixture mutation.' }
    $lastPark = $conflictOutput.LastIndexOf('PARKED')
    if ($lastPark -lt 0 -or $conflictOutput.Substring($lastPark).Contains('RESUMED')) { throw 'Removal conflict resumed the fixture with instruction replacements present.' }

    $normal.Process.Kill()
    $normal.Process.WaitForExit()
    Invoke-Case 'exited-process' 'inspect' $profile $normal 1 'exited'
    $finalHash = (Get-FileHash -LiteralPath $fixturePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($finalHash -ne $originalHash) { throw 'Fixture executable changed.' }
    $result = [pscustomobject]@{
        passed=$true; utc=[DateTime]::UtcNow.ToString('o'); fixture_sha256_before=$originalHash; fixture_sha256_after=$finalHash
        loader_sha256=(Get-FileHash -LiteralPath $loaderPath -Algorithm SHA256).Hash.ToLowerInvariant()
        cases=@($cases.ToArray()); limitation='Owned cooperative fixture only. No stock BO3 safe point or game patch.'
    }
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'result.json') -Encoding utf8
    Write-Output "PASS: $($cases.Count) loader E2E cases. Artifact: $OutputDirectory/result.json"
}
finally {
    foreach ($process in $processes) {
        if (-not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
        $process.Dispose()
    }
}
