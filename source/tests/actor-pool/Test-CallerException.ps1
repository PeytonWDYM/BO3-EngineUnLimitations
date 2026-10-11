#Requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$Manifest,
    [Parameter(Mandatory)][string]$Executable,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$target = [IO.Path]::GetFullPath($Output)
& $Python -B (Join-Path $PSScriptRoot 'Test-CallerException.py') --module $Manifest --executable $Executable --output $target
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
    @{passed = $true; staleCookieExitCode = $refusalCode; scope = 'The owned stale-cookie child exits before language cleanup or catch.'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $target 'refusal.json')
    $paths = @($fixture, $PSCommandPath, $binary, (Join-Path $target 'input-receipt.json'), (Join-Path $target 'result.json'), (Join-Path $target 'refusal.json'))
    $hashes = foreach ($path in $paths) { Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path, Hash }
    @{passed = $true; scope = 'Owned Windows native cookie handlers and C++ cleanup with the fixture CRT. The game CRT, real body, handler bridges and live registration remain unverified.'; files = @($hashes)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
