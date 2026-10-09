[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)

$ErrorActionPreference = 'Stop'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $visualStudio) { throw 'Install the Visual Studio C++ build tools.' }
$compilerRoot = (Get-ChildItem -LiteralPath (Join-Path $visualStudio 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdkVersion = (Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$env:INCLUDE = "$compilerRoot/include;$sdkRoot/Include/$sdkVersion/um;$sdkRoot/Include/$sdkVersion/shared;$sdkRoot/Include/$sdkVersion/ucrt;$sdkRoot/Include/$sdkVersion/winrt"
$env:LIB = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdkVersion/um/x64;$sdkRoot/Lib/$sdkVersion/ucrt/x64"
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$sourceRoot = Split-Path $PSScriptRoot -Parent
foreach ($tool in @(
    @{ name='AudioControl'; source=(Join-Path $PSScriptRoot 'AudioControl.cpp') },
    @{ name='GhidraFixture'; source=(Join-Path $sourceRoot 'tests/GhidraFixture.cpp') },
    @{ name='PoolFixture'; source=(Join-Path $sourceRoot 'tests/PoolFixture.cpp') }
)) {
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /MD /Od $tool.source "/Fe:$OutputDirectory/$($tool.name).exe" "/Fo:$OutputDirectory/$($tool.name).obj" /link ole32.lib uuid.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw "Compilation failed: $($tool.name)" }
}
