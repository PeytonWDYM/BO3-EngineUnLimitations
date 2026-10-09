[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
function PhysicalPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $resolved = [IO.Path]::GetPathRoot($full)
    foreach ($part in $full.Substring($resolved.Length).Split([char[]]@('\','/'),[StringSplitOptions]::RemoveEmptyEntries)) {
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
if ($outputPath -eq $repository -or $outputPath.StartsWith($repository+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Write driver evidence outside the repository.'
}
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $visualStudio) { throw 'Install the Visual Studio C++ build tools.' }
$compilerRoot = (Get-ChildItem -LiteralPath (Join-Path $visualStudio 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdkVersion = (Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$sourceRoot = Join-Path $repository 'source'
$common = @('Evidence.cpp','Format.cpp','Callbacks.cpp','Wasapi.cpp','DirectSound.cpp') | ForEach-Object { Join-Path $PSScriptRoot $_ }
$dependencies = @('Runtime.cpp','EndpointAdapters.cpp','AudioFamily.cpp','DirectSoundAdapter.cpp','SoundBufferFamily.cpp') | ForEach-Object { Join-Path $sourceRoot "launch/activation/$_" }
$dependencies += @('QuietRenderClient.cpp','QuietSoundBuffer.cpp','QuietFormat.cpp') | ForEach-Object { Join-Path $sourceRoot "launch/quiet/$_" }
$memory = @('ProviderRoots.cpp','ProviderAudio.cpp','ProviderDirectSound.cpp') | ForEach-Object { Join-Path $sourceRoot "tests/activation/$_" }
$memory += @('RenderSink.cpp','SoundSink.cpp','Report.cpp') | ForEach-Object { Join-Path $sourceRoot "tests/quiet/$_" }
$dependencyFiles = @($dependencies+$memory)
$dependencyFiles += @('launch/activation','launch/quiet') | ForEach-Object { Get-ChildItem -LiteralPath (Join-Path $sourceRoot $_) -Filter '*.h' -File | ForEach-Object FullName }
$dependencyFiles += @('tests/activation/Providers.h','tests/activation/ProviderCommon.h','tests/quiet/Fixture.h') | ForEach-Object { Join-Path $sourceRoot $_ }
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$header = Join-Path $outputPath 'Repository.h'
[IO.File]::WriteAllText($header, 'inline constexpr wchar_t RepositoryRoot[] = LR"('+$repository+')";'+[Environment]::NewLine)
try {
    $env:INCLUDE = "$outputPath;$compilerRoot/include;$sdkRoot/Include/$sdkVersion/um;$sdkRoot/Include/$sdkVersion/shared;$sdkRoot/Include/$sdkVersion/ucrt;$sdkRoot/Include/$sdkVersion/winrt"
    $env:LIB = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdkVersion/um/x64;$sdkRoot/Lib/$sdkVersion/ucrt/x64"
    $compiler = Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    $guardExe = Join-Path $outputPath 'AudioDriver-guards.exe'
    & $compiler /nologo /std:c++17 /EHsc /W4 /WX /MD /O2 "/Fo$outputPath/" "/Fe$guardExe" @common @dependencies @memory (Join-Path $PSScriptRoot 'Guards.cpp') /link ole32.lib uuid.lib dxguid.lib user32.lib
    if ($LASTEXITCODE) { throw "Guard compilation failed: $LASTEXITCODE" }
    $guardReport = Join-Path $outputPath 'guards.json'
    & $guardExe $guardReport
    if ($LASTEXITCODE) { throw "Owned driver guards failed: $LASTEXITCODE" }
    $physicalExe = Join-Path $outputPath 'AudioDriver-physical.exe'
    & $compiler /nologo /std:c++17 /EHsc /W4 /WX /MD /O2 "/Fo$outputPath/" "/Fe$physicalExe" @common @dependencies (Join-Path $PSScriptRoot 'DeviceSnapshot.cpp') (Join-Path $PSScriptRoot 'Physical.cpp') /link ole32.lib uuid.lib dxguid.lib user32.lib dsound.lib
    if ($LASTEXITCODE) { throw "Physical probe compilation failed: $LASTEXITCODE" }
    $hashes = [ordered]@{
        scope = 'Memory guards ran. The physical executable was built but was not run.'
        source = @(Get-ChildItem -LiteralPath $PSScriptRoot -File | ForEach-Object { @{name=$_.Name;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash} })
        dependencies = @($dependencyFiles | Sort-Object -Unique | ForEach-Object { @{path=[IO.Path]::GetRelativePath($repository,$_);sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash} })
        failureCases = (Get-FileHash -LiteralPath (Join-Path $repository 'research/audio-driver-failure-cases.txt') -Algorithm SHA256).Hash
        executables = @($guardExe,$physicalExe | ForEach-Object { @{name=[IO.Path]::GetFileName($_);sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash} })
        report = (Get-FileHash -LiteralPath $guardReport -Algorithm SHA256).Hash
        generatedRepositoryHeader = (Get-FileHash -LiteralPath $header -Algorithm SHA256).Hash
    }
    $hashes | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputPath 'hashes.json') -Encoding utf8
    Write-Output 'Memory guards passed. Physical probe built. No physical probe ran.'
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
