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
# pathlib resolves junctions in every existing path component.
$output = & $Python -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' $output
if ($LASTEXITCODE -ne 0) { throw 'The output path could not be resolved.' }
if ($output.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep fixture artifacts outside the repository.'
}
New-Item -ItemType Directory -Path (Join-Path $output 'bin') | Out-Null
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) { throw 'Install the Visual C++ x64 build tools.' }
$compiler = Get-ChildItem (Join-Path $installation 'VC\Tools\MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10'
$sdk = Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
try {
    $env:INCLUDE = "$($compiler.FullName)\include;$sdkRoot\Include\$($sdk.Name)\um;$sdkRoot\Include\$($sdk.Name)\shared;$sdkRoot\Include\$($sdk.Name)\ucrt"
    $env:LIB = "$($compiler.FullName)\lib\x64;$sdkRoot\Lib\$($sdk.Name)\um\x64;$sdkRoot\Lib\$($sdk.Name)\ucrt\x64"
    $fixture = Join-Path $output 'bin\StateFixture.exe'
    & (Join-Path $compiler.FullName 'bin\Hostx64\x64\cl.exe') /nologo /EHsc /W4 /WX /MD /std:c++20 /O2 (Join-Path $PSScriptRoot 'StateFixture.cpp') (Join-Path $PSScriptRoot 'StateNativeFixture.cpp') (Join-Path $repo 'source\patches\vm_pool\StateAdapter.cpp') (Join-Path $repo 'source\patches\vm_pool\NativeStateBridge.cpp') "/Fe:$fixture" "/Fo:$output\bin\\" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The native fixture build failed.' }
    & $fixture | Tee-Object -FilePath (Join-Path $output 'trace.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The state adapter fixture failed. See trace.txt.' }
    $dumpbin = Join-Path $compiler.FullName 'bin\Hostx64\x64\dumpbin.exe'
    $exports = & $dumpbin /exports $fixture | Out-String
    if ($LASTEXITCODE -ne 0) { throw 'The owned executable export inspection failed.' }
    $exports | Set-Content (Join-Path $output 'exports.txt')
    foreach ($symbol in 'Bo3VmStateBindings', 'ReadNativeState', 'WriteNativeState', 'InsertNativeStateKey', 'ClearNativeImportContext') {
        if ($exports -notmatch "\s$symbol(?:\s|$)") { throw "Missing C ABI export: $symbol" }
    }
    $symbols = & $dumpbin /symbols (Join-Path $output 'bin\NativeStateBridge.obj') | Out-String
    if ($LASTEXITCODE -ne 0) { throw 'The bridge object inspection failed.' }
    $symbols | Set-Content (Join-Path $output 'bridge-symbols.txt')
    if ($symbols -match '\.CRT\$XCU|dynamic initializer|dynamic atexit') { throw 'The bridge has an unexpected dynamic initializer.' }
    $receiptFiles = @(
        (Join-Path $PSScriptRoot 'StateFixture.cpp')
        (Join-Path $PSScriptRoot 'StateNativeFixture.cpp')
        (Join-Path $repo 'source\patches\vm_pool\StateAdapter.h')
        (Join-Path $repo 'source\patches\vm_pool\StateAdapter.cpp')
        (Join-Path $repo 'source\patches\vm_pool\NativeStateBridge.h')
        (Join-Path $repo 'source\patches\vm_pool\NativeStateBridge.cpp')
        $fixture
        (Join-Path $output 'trace.txt')
        (Join-Path $output 'exports.txt')
        (Join-Path $output 'bridge-symbols.txt')
    )
    $receipts = foreach ($path in $receiptFiles) { Get-FileHash -LiteralPath $path -Algorithm SHA256 | Select-Object Path, Hash }
    @{scope = 'Owned fixed-record callbacks and native bridge calls through owned image thunks. No BO3 launch. Captured native per-slot codecs require the separate instruction replay.'; files = @($receipts); passed = $true} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $output 'result.json')
} finally {
    $env:INCLUDE = $savedInclude
    $env:LIB = $savedLib
}
