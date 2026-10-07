param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
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
    $fixture = Join-Path $output 'bin\VmPoolFixture.exe'
    $object = Join-Path $output 'bin\VmPoolFixture.obj'
    & (Join-Path $compilerRoot.FullName 'bin\Hostx64\x64\cl.exe') /nologo /EHsc /W4 /WX /MD /Od (Join-Path $PSScriptRoot 'VmPoolFixture.cpp') "/Fe:$fixture" "/Fo:$object" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The native fixture build failed.' }
    & $Python (Join-Path $PSScriptRoot 'Verify-VmSampler.py') --fixture $fixture --output $output
    if ($LASTEXITCODE -ne 0) { throw 'The VM sampler E2E failed. See result.json.' }
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
