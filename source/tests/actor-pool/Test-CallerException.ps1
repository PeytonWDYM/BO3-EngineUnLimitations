#Requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$Manifest,
    [Parameter(Mandatory)][string]$Executable,
    [string]$Python = 'python',
    [ValidateSet(0, 8, 16, 24, 32, 40)][int]$TemporaryStack = 0,
    [ValidateSet(300,500)][int]$Actors=300
)
$ErrorActionPreference = 'Stop'
$target = [IO.Path]::GetFullPath($Output)
& $Python -B (Join-Path $PSScriptRoot 'Test-CallerException.py') --module $Manifest --executable $Executable --output $target --temporary-stack $TemporaryStack --actors $Actors
if ($LASTEXITCODE -ne 0) { throw 'The guarded caller-exception export failed.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler = Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk = Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude, $savedLib = $env:INCLUDE, $env:LIB
try {
    $env:INCLUDE = "$($compiler.FullName)/include;$sdkRoot/Include/$($sdk.Name)/um;$sdkRoot/Include/$($sdk.Name)/shared;$sdkRoot/Include/$($sdk.Name)/ucrt"
    $env:LIB = "$($compiler.FullName)/lib/x64;$sdkRoot/Lib/$($sdk.Name)/um/x64;$sdkRoot/Lib/$($sdk.Name)/ucrt/x64"
    $fixture = Join-Path $PSScriptRoot 'CallerExceptionFixture.cpp'
    $binary = Join-Path $target 'CallerExceptionFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MT /std:c++20 /O2 $fixture "/Fe:$binary" "/Fo:$target/" /link /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The Windows caller-exception fixture build failed.' }
    $input = Join-Path $target 'caller-exception.bin'
    & $binary $input correct | Tee-Object -FilePath (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) { throw 'The Windows caller-exception fixture failed.' }
    & $binary $input old-cookie
    $refusalCode = $LASTEXITCODE
    if ($refusalCode -ne 23) { throw "The stale caller cookie escaped its expected refusal: $refusalCode" }
    $refusals = @{staleCookieExitCode = $refusalCode}
    if ($TemporaryStack) {
        & $binary $input old-frame
        if ($LASTEXITCODE -ne 23) { throw 'Missing frame translation escaped cookie refusal.' }
        $refusals.missingFrameExitCode = $LASTEXITCODE
        & $binary $input old-pc
        if ($LASTEXITCODE -ne 25) { throw 'An unmodified stub code location escaped cleanup refusal.' }
        $refusals.unmodifiedControlPcExitCode = $LASTEXITCODE
        & $binary $input suppress-prolog | Tee-Object -FilePath (Join-Path $target 'suppression.json')
        if ($LASTEXITCODE -ne 0) { throw 'Native prolog handler suppression failed.' }
    }
    @{passed = $true; refusals = $refusals; scope = 'Owned stale-cookie, missing-frame and incorrect-code-location children exit at their expected refusals.'} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $target 'refusal.json')
    $paths = @($fixture, $PSCommandPath, $binary, (Join-Path $PSScriptRoot '../../patches/actor_pool/handler_bridge.hpp'),
        (Join-Path $target 'input-receipt.json'), (Join-Path $target 'result.json'), (Join-Path $target 'refusal.json'))
    if ($TemporaryStack) { $paths += (Join-Path $target 'suppression.json') }
    $hashes = foreach ($path in $paths) { Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path, Hash }
    @{passed = $true; scope = 'Owned Windows native cookie handlers and C++ cleanup with the fixture CRT and optional bridge prototype. Game CRT, real body, all native owners and live binding remain unverified.'; files = @($hashes)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
