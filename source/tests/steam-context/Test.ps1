param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$Python,[Parameter(Mandatory)][string]$Dependencies)
$ErrorActionPreference='Stop'
function PhysicalPath([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path); $resolved=[IO.Path]::GetPathRoot($full)
    foreach($part in $full.Substring($resolved.Length).Split([char[]]@('\','/'),[StringSplitOptions]::RemoveEmptyEntries)) {
        $resolved=Join-Path $resolved $part
        if(Test-Path -LiteralPath $resolved) { $target=(Get-Item -LiteralPath $resolved).ResolveLinkTarget($true); if($target) { $resolved=$target.FullName } }
    }
    return $resolved
}
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..'); $output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Use a private directory outside the repository.' }
if(Test-Path -LiteralPath $output) { throw 'Use a new private output directory.' }
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(!$installation) { throw 'Install the Visual C++ x64 build tools.' }
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'; $sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE; $savedLib=$env:LIB
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $bin=Join-Path $output 'bin'; New-Item -ItemType Directory -Path $bin | Out-Null
    @('#pragma once',"constexpr wchar_t kRepositoryRoot[]=L`"$($repo.Replace('\','\\'))`";") | Set-Content -LiteralPath (Join-Path $bin 'BuildIdentity.h') -Encoding ascii
    $sourceFiles=@((Join-Path $PSScriptRoot 'Runner.cpp'),(Join-Path $PSScriptRoot 'EnvironmentFixture.cpp'),
        (Join-Path $repo 'source/launch/enhanced/SteamContext.cpp'),(Join-Path $repo 'source/launch/preentry/Identity.cpp'))
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 "/I$bin" @sourceFiles "/Fo:$bin/" "/Fe:$bin/SteamContextFixture.exe" /link bcrypt.lib /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned Steam context fixture compilation failed.' }
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
$runner=Join-Path $output 'bin/SteamContextFixture.exe'; $binaryHash=(Get-FileHash -LiteralPath $runner).Hash
$sources=@(Get-ChildItem -LiteralPath $PSScriptRoot -File; Get-Item -LiteralPath (Join-Path $repo 'source/launch/enhanced/SteamContext.h'),(Join-Path $repo 'source/launch/enhanced/SteamContext.cpp')) | Get-FileHash | Select-Object Path,Hash
$receipts=foreach($case in @('parent','synthetic')) {
    $receipt=Join-Path $output "$case.json"; & $runner $case $receipt
    if($LASTEXITCODE -ne 0) { throw "Owned child environment failed: $case" }
    Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
}
& $Python (Join-Path $PSScriptRoot 'Replay.py') --sdk 'C:/Program Files (x86)/Steam/steamapps/common/Call of Duty Black Ops III/steam_api64.dll' --dependencies $Dependencies --output (Join-Path $output 'native-fastpath.json')
if($LASTEXITCODE -ne 0) { throw 'Exact read-only Steam fast-path replay failed.' }
if((Get-FileHash -LiteralPath $runner).Hash -ne $binaryHash) { throw 'Owned fixture binary changed during testing.' }
if(Compare-Object $sources ($sources.Path | Get-FileHash | Select-Object Path,Hash) -Property Path,Hash) { throw 'Owned context sources changed during testing.' }
@{scope='Four owned/read-only groups. No actual Steam SDK calls, BO3 launch, parent environment mutation or normal-file changes.';
    groupCount=4;binarySha256=$binaryHash;environmentReceipts=$receipts;nativeReplaySha256=(Get-FileHash (Join-Path $output 'native-fastpath.json')).Hash;sources=$sources
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $output 'result.json') -Encoding utf8
