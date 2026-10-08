[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Output,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$resultRoot = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $resultRoot) { throw 'Select a new test result folder.' }
New-Item -ItemType Directory -Path $resultRoot | Out-Null
$test = Join-Path $repo 'source/tests/patcher/test_transactions.py'
$log = Join-Path $resultRoot 'test-output.txt'
& $Python $test 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
$enhancedTest = Join-Path $repo 'source/tests/patcher/test_enhanced_launch.py'
$enhancedLog = Join-Path $resultRoot 'enhanced-output.txt'
& $Python $enhancedTest 2>&1 | Tee-Object -FilePath $enhancedLog
$enhancedCode = $LASTEXITCODE
if ($enhancedCode -ne 0) { $code = $enhancedCode }
$steamTest = Join-Path $repo 'source/tests/patcher/test_steam_launch.py'
$steamLog = Join-Path $resultRoot 'steam-output.txt'
& $Python $steamTest --evidence (Join-Path $resultRoot 'steam-fixtures') 2>&1 | Tee-Object -FilePath $steamLog
$steamCode = $LASTEXITCODE
if ($steamCode -ne 0) { $code = $steamCode }
$result = [ordered]@{
    schema = 1
    suite = 'owned-patcher-transactions'
    status = $(if ($code -eq 0) { 'passed' } else { 'failed' })
    exitCode = $code
    timestampUtc = [DateTime]::UtcNow.ToString('o')
    testSourceSha256 = (Get-FileHash -LiteralPath $test -Algorithm SHA256).Hash.ToLowerInvariant()
    fixtureScope = 'Owned temporary files. No game or mod assets.'
    logSha256 = (Get-FileHash -LiteralPath $log -Algorithm SHA256).Hash.ToLowerInvariant()
    enhancedTestSourceSha256 = (Get-FileHash -LiteralPath $enhancedTest -Algorithm SHA256).Hash.ToLowerInvariant()
    enhancedLogSha256 = (Get-FileHash -LiteralPath $enhancedLog -Algorithm SHA256).Hash.ToLowerInvariant()
    steamTestSourceSha256 = (Get-FileHash -LiteralPath $steamTest -Algorithm SHA256).Hash.ToLowerInvariant()
    steamLogSha256 = (Get-FileHash -LiteralPath $steamLog -Algorithm SHA256).Hash.ToLowerInvariant()
}
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $resultRoot 'result.json') -Encoding utf8
if ($code -ne 0) { throw "Patcher tests failed with exit code $code." }
