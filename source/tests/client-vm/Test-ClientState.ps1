param(
    [Parameter(Mandatory = $true)][string]$Output,
    [string]$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $SourceRoot).Path
$target = [IO.Path]::GetFullPath($Output)
if ($target.Equals($source, [StringComparison]::OrdinalIgnoreCase) -or $target.StartsWith($source + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Use an output folder outside the source tree.'
}
if (Test-Path -LiteralPath $target) { throw 'Use a new output folder.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler = Get-ChildItem (Join-Path $installation 'VC\Tools\MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10'
$sdk = Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude, $savedLib = $env:INCLUDE, $env:LIB
New-Item -ItemType Directory -Path $target | Out-Null
try {
    $env:INCLUDE = "$($compiler.FullName)\include;$sdkRoot\Include\$($sdk.Name)\um;$sdkRoot\Include\$($sdk.Name)\shared;$sdkRoot\Include\$($sdk.Name)\ucrt"
    $env:LIB = "$($compiler.FullName)\lib\x64;$sdkRoot\Lib\$($sdk.Name)\um\x64;$sdkRoot\Lib\$($sdk.Name)\ucrt\x64"
    $fixture = Join-Path $source 'source\tests\client-vm\ClientStateFixture.cpp'
    $adapter = Join-Path $source 'source\patches\vm_pool\StateAdapter.cpp'
    $executable = Join-Path $target 'ClientStateFixture.exe'
    & (Join-Path $compiler.FullName 'bin\Hostx64\x64\cl.exe') /nologo /EHsc /W4 /WX /MD /std:c++20 /O2 $fixture $adapter "/Fe:$executable" "/Fo:$target\\" /link /INCREMENTAL:NO 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The client state fixture build failed.' }
    & $executable | Tee-Object -FilePath (Join-Path $target 'trace.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The client state fixture failed.' }
    $files = @($fixture, $adapter, (Join-Path $source 'source\patches\vm_pool\StateAdapter.h'), $executable, (Join-Path $target 'trace.txt'))
    $hashes = foreach ($path in $files) { Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path, Hash }
    @{passed = $true; scope = 'Owned fixed-record callbacks. Native BO3 codecs require a separate replay.'; files = @($hashes)} | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $target 'receipt.json')
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
