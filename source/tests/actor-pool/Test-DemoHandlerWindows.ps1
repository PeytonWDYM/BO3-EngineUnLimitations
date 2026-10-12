#Requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$Manifest,
    [Parameter(Mandatory)][string]$Executable,
    [string]$Python='python'
)
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($Output)
& $Python -B (Join-Path $PSScriptRoot 'Test-DemoHandlerWindows.py') --module $Manifest --executable $Executable --output $target
if ($LASTEXITCODE -ne 0) {throw 'The native GS fixture export failed.'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler=Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude,$savedLib=$env:INCLUDE,$env:LIB
try {
    $env:INCLUDE="$($compiler.FullName)/include;$sdkRoot/Include/$($sdk.Name)/um;$sdkRoot/Include/$($sdk.Name)/shared;$sdkRoot/Include/$($sdk.Name)/ucrt"
    $env:LIB="$($compiler.FullName)/lib/x64;$sdkRoot/Lib/$($sdk.Name)/um/x64;$sdkRoot/Lib/$($sdk.Name)/ucrt/x64"
    $fixture=Join-Path $PSScriptRoot 'DemoHandlerFixture.cpp'
    $binary=Join-Path $target 'DemoHandlerFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MT /std:c++20 /O2 $fixture "/Fe:$binary" "/Fo:$target/" /link /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) {throw 'The native GS fixture build failed.'}
    $input=Join-Path $target 'demo-gs-windows.bin'
    & $binary $input correct | Tee-Object -FilePath (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) {throw 'The native GS Windows dispatch fixture failed.'}
    $refusals=foreach ($mode in @('old-cookie','high-cookie')) {
        & $binary $input $mode
        if ($LASTEXITCODE -ne 23) {throw "The native GS $mode control escaped its expected failure: $LASTEXITCODE"}
        @{mode=$mode;exitCode=$LASTEXITCODE}
    }
    @{passed=$true;cases=@($refusals)} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $target 'refusal.json')
    $paths=@($fixture,$PSCommandPath,$binary,(Join-Path $target 'input-receipt.json'),(Join-Path $target 'result.json'),(Join-Path $target 'refusal.json'))
    $hashes=foreach ($path in $paths) {Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path,Hash}
    @{passed=$true;scope='Owned Windows native GS handler/common/cookie execution with native demo frames and authored body/exception/failure bindings. Real game registration remains unverified.';files=@($hashes)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {
    $env:INCLUDE=$savedInclude
    $env:LIB=$savedLib
}
