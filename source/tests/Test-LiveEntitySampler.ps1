[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$Fixture,
    [Parameter(Mandatory)][string]$Profiles,
    [Parameter(Mandatory)][string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\','/')
if ($output -eq $repo -or $output.StartsWith($repo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Write live sampler evidence outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Choose a new E2E output directory.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $visualStudio) { throw 'Install the Visual Studio C++ build tools.' }
$compilerRoot = (Get-ChildItem -LiteralPath (Join-Path $visualStudio 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdkVersion = (Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$env:INCLUDE = "$compilerRoot/include;$sdkRoot/Include/$sdkVersion/um;$sdkRoot/Include/$sdkVersion/shared;$sdkRoot/Include/$sdkVersion/ucrt"
$env:LIB = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdkVersion/um/x64;$sdkRoot/Lib/$sdkVersion/ucrt/x64"
$bin = Join-Path $output 'bin'
New-Item -ItemType Directory -Path $bin -Force | Out-Null
$dynamicFixture = Join-Path $bin 'LiveEntityFixture.exe'
& (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /MD /Od (Join-Path $PSScriptRoot 'Test-LiveEntityFixture.cpp') "/Fe:$dynamicFixture" "/Fo:$bin/LiveEntityFixture.obj" /link /INCREMENTAL:NO
if ($LASTEXITCODE -ne 0) { throw 'The moving-state fixture did not compile.' }
& $Python (Join-Path $PSScriptRoot 'Test-LiveEntitySampler.py') --fixture $Fixture --profiles $Profiles --dynamic-fixture $dynamicFixture --output (Join-Path $output 'results')
if ($LASTEXITCODE -ne 0) { throw 'The live entity sampler E2E failed.' }
