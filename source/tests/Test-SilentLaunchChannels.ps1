[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OutputDirectory,
    [ValidatePattern('^[A-Za-z0-9_-]+\.exe$')][string]$ExecutableName = 'SilentLaunchChannels.exe',
    [ValidateSet('StartProcess','Direct')][string]$Invocation = 'StartProcess'
)

$ErrorActionPreference = 'Stop'
$repository = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$resolvedOutput = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\','/')
if ($resolvedOutput -eq $repository -or $resolvedOutput.StartsWith($repository + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Write audio E2E evidence outside the repository.'
}
if (Test-Path -LiteralPath $resolvedOutput) { throw 'Use a new output directory for each E2E run.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $visualStudio) { throw 'Install the Visual Studio C++ build tools.' }
$compilerRoot = (Get-ChildItem -LiteralPath (Join-Path $visualStudio 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdkVersion = (Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$oldInclude = $env:INCLUDE
$oldLib = $env:LIB
New-Item -ItemType Directory -Path $resolvedOutput | Out-Null
$probeDirectory = Join-Path $resolvedOutput 'probe'
$independentDirectory = Join-Path $resolvedOutput 'independent'
New-Item -ItemType Directory -Path $probeDirectory,$independentDirectory | Out-Null
$probe = Join-Path $probeDirectory $ExecutableName
$independent = Join-Path $independentDirectory $ExecutableName
$source = Join-Path (Split-Path $PSScriptRoot -Parent) 'launch/SilentLaunchChannels.cpp'

try {
    $env:INCLUDE = "$compilerRoot/include;$sdkRoot/Include/$sdkVersion/um;$sdkRoot/Include/$sdkVersion/shared;$sdkRoot/Include/$sdkVersion/ucrt;$sdkRoot/Include/$sdkVersion/winrt"
    $env:LIB = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdkVersion/um/x64;$sdkRoot/Lib/$sdkVersion/ucrt/x64"
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /std:c++17 /W4 /MD /O2 $source "/Fe:$probe" "/Fo:$probeDirectory/SilentLaunchChannels.obj" /link ole32.lib uuid.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The audio probe did not compile.' }
} finally {
    $env:INCLUDE = $oldInclude
    $env:LIB = $oldLib
}
Copy-Item -LiteralPath $probe -Destination $independent
$commands = [Collections.Generic.List[object]]::new()
$checks = [Collections.Generic.List[object]]::new()

function Invoke-Probe([string]$Executable, [string]$Action, [string]$Name) {
    $stdout = Join-Path $resolvedOutput "$Name.jsonl"
    $stderr = Join-Path $resolvedOutput "$Name.stderr.txt"
    $started = [DateTime]::UtcNow.ToString('o')
    if ($Invocation -eq 'Direct') {
        $lines = & $Executable $Action 2>$stderr
        $exitCode = $LASTEXITCODE
        $lines | Set-Content -LiteralPath $stdout -Encoding utf8
        $rows = @($lines | ForEach-Object { $_ | ConvertFrom-Json })
        $processId = $rows[0].pid
    } else {
        $process = Start-Process -FilePath $Executable -ArgumentList $Action -PassThru -Wait -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        $exitCode = $process.ExitCode
        $processId = $process.Id
        $rows = @(Get-Content -LiteralPath $stdout | ForEach-Object { $_ | ConvertFrom-Json })
    }
    $commands.Add(@{ executable=$Executable; action=$Action; pid=$processId; invocation=$Invocation; startedUtc=$started; exitCode=$exitCode; stdout=$stdout; stderr=$stderr })
    if ($exitCode -ne 0) { throw "Audio probe failed: $Name. Read $stderr." }
    return $rows
}

function Add-Check([string]$Name, [bool]$Passed) {
    $checks.Add(@{ name=$Name; passed=$Passed })
}

function Zero-Channels($Rows) {
    $sessions = @($Rows | Where-Object { $_.kind -eq 'session' })
    return $sessions.Count -gt 0 -and @($sessions | Where-Object { $_.channels.Count -eq 0 -or @($_.channels | Where-Object { $_ -ne 0 }).Count -gt 0 }).Count -eq 0
}

$before = Invoke-Probe $probe 'endpoint-snapshot' 'endpoint-before'
$baseline = Invoke-Probe $independent 'probe-default' 'independent-before'
try {
    $seed = Invoke-Probe $probe 'seed-default' 'seed'
    $first = Invoke-Probe $probe 'probe-default' 'restart-1'
    $second = Invoke-Probe $probe 'probe-default' 'restart-2'
    $other = Invoke-Probe $independent 'probe-default' 'independent-after'
    Add-Check 'Seed sets every default-session channel to zero.' (Zero-Channels @($seed | Where-Object phase -eq 'after'))
    Add-Check 'A new process inherits zero channel volume before a master reset.' (Zero-Channels @($first | Where-Object phase -eq 'initial'))
    Add-Check 'Master one and mute false preserve zero channel volume.' (Zero-Channels @($first | Where-Object phase -eq 'after'))
    Add-Check 'The first restarted process has zero channel volume at activation.' (Zero-Channels @($first | Where-Object phase -eq 'active'))
    Add-Check 'The first restarted process has zero channel volume after 40 milliseconds.' (Zero-Channels @($first | Where-Object phase -eq 'settled'))
    Add-Check 'A second restart retains zero channel volume.' (Zero-Channels $second)
    Add-Check 'Each endpoint resets master volume and mute as requested.' (@($first | Where-Object { $_.phase -eq 'after' -and ($_.volume -ne 1 -or $_.muted) }).Count -eq 0)
    $baselineChannels = @($baseline | Where-Object phase -eq 'after' | Sort-Object endpoint | Select-Object endpoint,channels | ConvertTo-Json -Depth 5 -Compress)
    $otherChannels = @($other | Where-Object phase -eq 'after' | Sort-Object endpoint | Select-Object endpoint,channels | ConvertTo-Json -Depth 5 -Compress)
    Add-Check 'The same filename in another directory retains independent channel settings.' ($baselineChannels[0] -ceq $otherChannels[0])
    Add-Check 'Separate process launches use separate PIDs.' (@($commands | Where-Object action -eq 'probe-default' | Select-Object -ExpandProperty pid -Unique).Count -eq 4)
} finally {
    $reset = Invoke-Probe $probe 'reset-default' 'reset'
    $independentReset = Invoke-Probe $independent 'reset-default' 'independent-reset'
}
$after = Invoke-Probe $probe 'endpoint-snapshot' 'endpoint-after'
$beforeState = $before | Sort-Object endpoint | Select-Object endpoint,volume,muted | ConvertTo-Json -Depth 5 -Compress
$afterState = $after | Sort-Object endpoint | Select-Object endpoint,volume,muted | ConvertTo-Json -Depth 5 -Compress
Add-Check 'Endpoint volume and mute remain unchanged.' ($beforeState -ceq $afterState)
Add-Check 'The fixture returns to unit channel volume.' (@($reset | Where-Object { $_.phase -eq 'after' -and @($_.channels | Where-Object { $_ -ne 1 }).Count -gt 0 }).Count -eq 0)

$report = @{ schemaVersion=1; createdUtc=[DateTime]::UtcNow.ToString('o'); passed=@($checks | Where-Object { -not $_.passed }).Count -eq 0; scope='Silent native WASAPI fixture only. No BO3 launch or BO3 guarantee.'; executableSha256=(Get-FileHash -LiteralPath $probe -Algorithm SHA256).Hash; endpointCount=$before.Count; commands=$commands; checks=$checks; limitations=@('The game must use the seeded default shared-mode session.', 'The game must not reset session channel volumes.', 'New endpoints and exclusive-mode playback require separate validation.') }
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $resolvedOutput 'report.json') -Encoding utf8
$report | ConvertTo-Json -Depth 8
if (-not $report.passed) { throw 'The session channel E2E probe found a failed condition.' }
