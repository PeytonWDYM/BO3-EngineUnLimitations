#Requires -Version 7.0
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo = PhysicalPath (Join-Path $PSScriptRoot '../../..')
$output = PhysicalPath $OutputDirectory
if ($output.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep fixture artifacts outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory.' }
New-Item -ItemType Directory -Path (Join-Path $output 'bin') | Out-Null
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) { throw 'Install the Visual C++ x64 build tools.' }
$compilerRoot = Get-ChildItem (Join-Path $installation 'VC\Tools\MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10'
$sdk = Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
try {
    $env:INCLUDE = "$($compilerRoot.FullName)\include;$sdkRoot\Include\$($sdk.Name)\um;$sdkRoot\Include\$($sdk.Name)\shared;$sdkRoot\Include\$($sdk.Name)\ucrt"
    $env:LIB = "$($compilerRoot.FullName)\lib\x64;$sdkRoot\Lib\$($sdk.Name)\um\x64;$sdkRoot\Lib\$($sdk.Name)\ucrt\x64"
    $compiler = Join-Path $compilerRoot.FullName 'bin\Hostx64\x64\cl.exe'
    $bin = Join-Path $output 'bin'
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MD /LD (Join-Path $PSScriptRoot 'EnhancedOverlayHelper.cpp') "/Fe:$bin\Bo3EnhancedHelper.dll" "/Fo:$bin\EnhancedOverlayHelper.obj" /link /INCREMENTAL:NO "/IMPLIB:$bin\Bo3EnhancedHelper.lib"
    if ($LASTEXITCODE -ne 0) { throw 'The owned helper build failed.' }
    $fixture = Join-Path $bin 'EnhancedOverlayFixture.exe'
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MD (Join-Path $PSScriptRoot 'EnhancedOverlayFixture.cpp') "/Fe:$fixture" "/Fo:$bin\EnhancedOverlayFixture.obj" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The owned fixture build failed.' }
    & $Python (Join-Path $PSScriptRoot 'Verify-EnhancedSession.py') --fixture $fixture --output $output
    if ($LASTEXITCODE -ne 0) { throw 'Enhanced enrollment E2E failed.' }
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
