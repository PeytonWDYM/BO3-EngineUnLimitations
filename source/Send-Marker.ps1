[CmdletBinding()]
param(
    [ValidateSet('match-start','fire-start','fire-end','connection-interrupted','dump','note','stop')]
    [string]$Action = 'note',
    [string]$OutputRoot = '',
    [ValidateSet('Unknown','Solo','Coop')][string]$Mode = 'Unknown',
    [ValidateRange(0,4)][int]$PlayerCount = 0,
    [ValidateSet('Unknown','Host','Client')][string]$HostRole = 'Unknown',
    [string]$Map = '',
    [ValidateRange(0,10000)][int]$Round = 0,
    [string]$Note = ''
)

$ErrorActionPreference = 'Stop'
if (-not $OutputRoot) { $OutputRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'research/captures/live' }
$state = Get-Content -LiteralPath (Join-Path $OutputRoot 'active.json') -Raw | ConvertFrom-Json
$recorder = Get-Process -Id $state.recorderPid -ErrorAction Stop
if ($recorder.StartTime.ToUniversalTime().ToString('o') -ne $state.recorderStartedUtc) { throw 'The recorder is no longer active.' }
$requestDirectory = Join-Path $state.sessionDirectory 'requests'
$temporary = Join-Path $requestDirectory ([Guid]::NewGuid().ToString('N') + '.tmp')
[ordered]@{
    utc = [DateTime]::UtcNow.ToString('o')
    action = $Action
    data = @{ mode = $Mode; playerCount = $PlayerCount; hostRole = $HostRole; map = $Map; round = $Round; note = $Note }
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -LiteralPath $temporary -Destination ([IO.Path]::ChangeExtension($temporary, '.json'))
Write-Output "Queued: $Action"
