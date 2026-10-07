[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory, [switch]$IncludeE2EFaultFixture)

$ErrorActionPreference = 'Stop'
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $visualStudio) { throw 'Install the Visual Studio C++ build tools.' }
$compilerRoot = (Get-ChildItem -LiteralPath (Join-Path $visualStudio 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdkVersion = (Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$originalInclude = $env:INCLUDE
$originalLib = $env:LIB
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$compiler = Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
try {
    $env:INCLUDE = "$compilerRoot/include;$sdkRoot/Include/$sdkVersion/um;$sdkRoot/Include/$sdkVersion/shared;$sdkRoot/Include/$sdkVersion/ucrt"
    $env:LIB = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdkVersion/um/x64;$sdkRoot/Lib/$sdkVersion/ucrt/x64"
    $sources = @('Main.cpp', 'Profile.cpp', 'Target.cpp', 'MemoryPatch.cpp', 'Session.cpp') | ForEach-Object { Join-Path $PSScriptRoot $_ }
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 @sources "/Fe:$OutputDirectory/PatchLoader.exe" "/Fo:$OutputDirectory/" /link bcrypt.lib /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
    if ($LASTEXITCODE -ne 0) { throw 'PatchLoader compilation failed.' }
    if ($IncludeE2EFaultFixture) {
        & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 /DPATCH_LOADER_E2E_FAIL_AFTER_FIRST_WRITE @sources "/Fe:$OutputDirectory/PatchLoaderRollbackFixture.exe" "/Fo:$OutputDirectory/" /link bcrypt.lib /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
        if ($LASTEXITCODE -ne 0) { throw 'PatchLoader rollback fixture compilation failed.' }
        & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 /DPATCH_LOADER_E2E_DELAY_RECORD_WRITES @sources "/Fe:$OutputDirectory/PatchLoaderSafePointFixture.exe" "/Fo:$OutputDirectory/" /link bcrypt.lib /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
        if ($LASTEXITCODE -ne 0) { throw 'PatchLoader safe-point fixture compilation failed.' }
    }
    $fixture = Join-Path $PSScriptRoot '../tests/PatchLoaderFixture.cpp'
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 $fixture "/Fe:$OutputDirectory/PatchLoaderFixture.exe" "/Fo:$OutputDirectory/PatchLoaderFixture.obj" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
    if ($LASTEXITCODE -ne 0) { throw 'PatchLoaderFixture compilation failed.' }
}
finally {
    $env:INCLUDE = $originalInclude
    $env:LIB = $originalLib
}
