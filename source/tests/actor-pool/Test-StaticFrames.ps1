#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Output,[Parameter(Mandatory)][string]$Manifest,[Parameter(Mandatory)][string]$Executable,[string]$Python='python',[ValidateSet(300,500)][int]$Actors=500)
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($Output)
& $Python -B (Join-Path $PSScriptRoot 'Test-StaticFrames.py') --module $Manifest --executable $Executable --output $target --actors $Actors
if ($LASTEXITCODE -ne 0) {throw 'The static frame template export failed.'}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler=Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude,$savedLib=$env:INCLUDE,$env:LIB
try {
    $env:INCLUDE="$($compiler.FullName)/include;$sdkRoot/Include/$($sdk.Name)/um;$sdkRoot/Include/$($sdk.Name)/shared;$sdkRoot/Include/$($sdk.Name)/ucrt"
    $env:LIB="$($compiler.FullName)/lib/x64;$sdkRoot/Lib/$($sdk.Name)/um/x64;$sdkRoot/Lib/$($sdk.Name)/ucrt/x64"
    $assembly=Join-Path $target 'ResetTemplate.asm'
    $object=Join-Path $target 'ResetTemplate.obj'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/ml64.exe') /nologo /c "/Fo$object" $assembly
    if ($LASTEXITCODE -ne 0) {throw 'Static frame assembly failed.'}
    $flags=@('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2',"/Fo:$target/")
    $dll=Join-Path $target 'StaticFrameDll.dll'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') @flags /LD (Join-Path $PSScriptRoot 'StaticFrameDll.cpp') $object "/Fe:$dll" /link /INCREMENTAL:NO /Brepro /EXPORT:Bo3HistoryResetTemplate /EXPORT:Bo3OwnedMemsetRelay /EXPORT:Bo3OwnedClearTarget
    if ($LASTEXITCODE -ne 0) {throw 'Static frame DLL build failed.'}
    $binary=Join-Path $target 'StaticFrameFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') @flags (Join-Path $PSScriptRoot 'StaticFrameFixture.cpp') "/Fe:$binary" /link /INCREMENTAL:NO /Brepro
    if ($LASTEXITCODE -ne 0) {throw 'Static frame fixture build failed.'}
    & $binary $dll (Join-Path $target 'template.bin') | Tee-Object -FilePath (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) {throw 'Static frame fixture failed.'}
    $paths=@($PSCommandPath,(Join-Path $PSScriptRoot 'StaticFrameDll.cpp'),(Join-Path $PSScriptRoot 'StaticFrameFixture.cpp'),$assembly,$binary,$dll,(Join-Path $target 'input-receipt.json'),(Join-Path $target 'result.json'))
    @{passed=$true;gameLaunches=0;dynamicRegistrations=0;files=@($paths | ForEach-Object {Get-FileHash -LiteralPath $_ | Select-Object Path,Hash})} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
} finally {$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
