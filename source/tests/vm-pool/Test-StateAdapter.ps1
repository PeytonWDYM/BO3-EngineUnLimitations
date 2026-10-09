param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../../../scripts/release/Platform.ps1')
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-WithinPath $output $repo) {
    throw 'Keep fixture artifacts outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory.' }
# pathlib resolves junctions in every existing path component.
$output = & $Python -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' $output
if ($LASTEXITCODE -ne 0) { throw 'The output path could not be resolved.' }
if (Test-WithinPath $output $repo) {
    throw 'Keep fixture artifacts outside the repository.'
}
New-Item -ItemType Directory -Path (Join-Path $output 'bin') | Out-Null
$msvc = Get-MsvcToolchain
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
try {
    if ($msvc.Include) { $env:INCLUDE = $msvc.Include; $env:LIB = $msvc.Lib }
    $fixture = Join-Path $output 'bin/StateFixture.exe'
    & $msvc.Cl /nologo /EHsc /W4 /WX /MD /std:c++20 /O2 (Join-Path $PSScriptRoot 'StateFixture.cpp') (Join-Path $PSScriptRoot 'StateNativeFixture.cpp') (Join-Path $repo 'source/patches/vm_pool/StateAdapter.cpp') (Join-Path $repo 'source/patches/vm_pool/NativeStateBridge.cpp') "/Fe$fixture" "/Fo$output/bin/" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The native fixture build failed.' }
    Invoke-Windows $fixture | Tee-Object -FilePath (Join-Path $output 'trace.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The state adapter fixture failed. See trace.txt.' }
    $exports = & $msvc.Dumpbin /exports $fixture | Out-String
    if ($LASTEXITCODE -ne 0) { throw 'The owned executable export inspection failed.' }
    $exports | Set-Content (Join-Path $output 'exports.txt')
    foreach ($symbol in 'Bo3VmStateBindings', 'ReadNativeState', 'WriteNativeState', 'InsertNativeStateKey', 'ClearNativeImportContext') {
        if ($exports -notmatch "\s$symbol(?:\s|$)") { throw "Missing C ABI export: $symbol" }
    }
    $symbols = & $msvc.Dumpbin /symbols (Join-Path $output 'bin/NativeStateBridge.obj') | Out-String
    if ($LASTEXITCODE -ne 0) { throw 'The bridge object inspection failed.' }
    $symbols | Set-Content (Join-Path $output 'bridge-symbols.txt')
    if ($symbols -match '\.CRT\$XCU|dynamic initializer|dynamic atexit') { throw 'The bridge has an unexpected dynamic initializer.' }
    $receiptFiles = @(
        (Join-Path $PSScriptRoot 'StateFixture.cpp')
        (Join-Path $PSScriptRoot 'StateNativeFixture.cpp')
        (Join-Path $repo 'source/patches/vm_pool/StateAdapter.h')
        (Join-Path $repo 'source/patches/vm_pool/StateAdapter.cpp')
        (Join-Path $repo 'source/patches/vm_pool/NativeStateBridge.h')
        (Join-Path $repo 'source/patches/vm_pool/NativeStateBridge.cpp')
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
