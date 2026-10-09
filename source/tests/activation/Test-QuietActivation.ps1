[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory, [switch]$Baseline)
$ErrorActionPreference = 'Stop'
function PhysicalPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $resolved = [IO.Path]::GetPathRoot($full)
    foreach ($part in $full.Substring($resolved.Length).Split([char[]]@('\', '/'), [StringSplitOptions]::RemoveEmptyEntries)) {
        $resolved = Join-Path $resolved $part
        if (Test-Path -LiteralPath $resolved) {
            $target = (Get-Item -LiteralPath $resolved).ResolveLinkTarget($true)
            if ($target) { $resolved = $target.FullName }
        }
    }
    return $resolved
}
$repository = PhysicalPath (Join-Path $PSScriptRoot '../../..')
$outputPath = PhysicalPath $OutputDirectory
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
$sourceRoot = Join-Path $repository 'source'
$sources = @('Main.cpp','Harness.cpp','ProviderRoots.cpp','ProviderAudio.cpp','ProviderDirectSound.cpp','WasapiScenarios.cpp','OtherScenarios.cpp') | ForEach-Object { Join-Path $PSScriptRoot $_ }
$sources += @('RenderSink.cpp','SoundSink.cpp','Report.cpp') | ForEach-Object { Join-Path $sourceRoot "tests/quiet/$_" }
$defines = @()
if ($Baseline) { $defines += '/DACTIVATION_BASELINE' }
else {
    $sources += @('Runtime.cpp','EndpointAdapters.cpp','AudioFamily.cpp','DirectSoundAdapter.cpp','SoundBufferFamily.cpp') | ForEach-Object { Join-Path $sourceRoot "launch/activation/$_" }
    $sources += @('QuietRenderClient.cpp','QuietSoundBuffer.cpp','QuietFormat.cpp') | ForEach-Object { Join-Path $sourceRoot "launch/quiet/$_" }
}
$mode = if ($Baseline) { 'baseline' } else { 'protected' }
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$exe = Join-Path $outputPath "QuietActivation-$mode.exe"
$reportPath = Join-Path $outputPath "$mode.json"
try {
    $env:INCLUDE = "$compilerRoot/include;$sdkRoot/Include/$sdkVersion/um;$sdkRoot/Include/$sdkVersion/shared;$sdkRoot/Include/$sdkVersion/ucrt;$sdkRoot/Include/$sdkVersion/winrt"
    $env:LIB = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdkVersion/um/x64;$sdkRoot/Lib/$sdkVersion/ucrt/x64"
    Push-Location -LiteralPath $outputPath
    try {
        & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MD /std:c++17 /O2 @defines @sources "/Fe:$exe" /link ole32.lib uuid.lib dxguid.lib /INCREMENTAL:NO
        if ($LASTEXITCODE -ne 0) { throw 'Activation fixture compilation failed.' }
        & $exe $reportPath
        $fixtureExit = $LASTEXITCODE
    } finally { Pop-Location }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if ($Baseline) {
        if ($fixtureExit -ne 1 -or $report.failed -lt 5) { throw 'The unprotected activation baseline did not show expected failures.' }
    } elseif ($fixtureExit -ne 0 -or $report.failed -ne 0) { throw "Activation fixture failed. See $reportPath" }
    [pscustomobject]@{ mode=$mode; passed=$report.passed; failed=$report.failed; fixtureExit=$fixtureExit; artifact=$reportPath }
} finally { $env:INCLUDE = $savedInclude; $env:LIB = $savedLib }
