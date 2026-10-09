[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OutputDirectory,
    [switch]$Baseline
)

$ErrorActionPreference = 'Stop'
$repository = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
$repository = [IO.Path]::GetFullPath($repository).TrimEnd('\','/')
$outputPath = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\','/')
if ($outputPath -eq $repository -or $outputPath.StartsWith($repository + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Write audio E2E evidence outside the repository.'
}
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $visualStudio) { throw 'Install the Visual Studio C++ build tools.' }
$compilerRoot = (Get-ChildItem -LiteralPath (Join-Path $visualStudio 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdkVersion = (Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
$fixtureRoot = $PSScriptRoot
$boundaryRoot = Join-Path (Split-Path (Split-Path $fixtureRoot -Parent) -Parent) 'launch/quiet'
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$mode = if ($Baseline) { 'baseline' } else { 'protected' }
$exe = Join-Path $outputPath "QuietBoundary-$mode.exe"
$reportPath = Join-Path $outputPath "$mode.json"
$sources = @('Main.cpp', 'RenderSink.cpp', 'SoundSink.cpp', 'Report.cpp', 'RenderScenarios.cpp', 'SoundScenarios.cpp') | ForEach-Object { Join-Path $fixtureRoot $_ }
$defines = @()
if ($Baseline) { $defines += '/DQUIET_BOUNDARY_BASELINE' }
else { $sources += @('QuietRenderClient.cpp', 'QuietSoundBuffer.cpp', 'QuietFormat.cpp') | ForEach-Object { Join-Path $boundaryRoot $_ } }
try {
    $env:INCLUDE = "$compilerRoot/include;$sdkRoot/Include/$sdkVersion/um;$sdkRoot/Include/$sdkVersion/shared;$sdkRoot/Include/$sdkVersion/ucrt;$sdkRoot/Include/$sdkVersion/winrt"
    $env:LIB = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdkVersion/um/x64;$sdkRoot/Lib/$sdkVersion/ucrt/x64"
    Push-Location -LiteralPath $outputPath
    try {
        & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MD /std:c++17 /O2 @defines @sources "/Fe:$exe" /link ole32.lib uuid.lib dxguid.lib /INCREMENTAL:NO
        if ($LASTEXITCODE -ne 0) { throw 'Native fixture compilation failed.' }
        & $exe $reportPath
        $fixtureExit = $LASTEXITCODE
    } finally { Pop-Location }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if ($Baseline) {
        if ($fixtureExit -ne 1 -or -not $report.expectedFailure -or $report.failed -lt 5) { throw 'The unprotected baseline did not show the expected audio failures.' }
    } elseif ($fixtureExit -ne 0 -or $report.failed -ne 0) { throw "The protected fixture failed. See $reportPath" }
    [pscustomobject]@{ mode=$mode; passed=$report.passed; failed=$report.failed; fixtureExit=$fixtureExit; artifact=$reportPath }
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
