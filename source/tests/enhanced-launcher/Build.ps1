param([Parameter(Mandatory)][string]$ProductionBuild, [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][string]$DetoursRoot)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo = PhysicalPath (Join-Path $PSScriptRoot '../../..')
$output = PhysicalPath $OutputDirectory
if ($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep owned binaries outside the repository.' }
if (Test-Path -LiteralPath $output) { throw 'Use a new build directory.' }
$production = PhysicalPath $ProductionBuild
$receipt = Get-Content -LiteralPath "$production/build-receipt.json" -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath "$production/Bo3EnhancedHelper.dll").Hash.ToLowerInvariant() -ne $receipt.helperSha256) { throw 'The production helper differs from its receipt.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot = (Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk = (Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
try {
    $env:INCLUDE = "$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    New-Item -ItemType Directory -Path $output | Out-Null
    $compiler = Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    $flags = @('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2',"/I$output","/I$DetoursRoot/include")
    & $compiler @flags (Join-Path $PSScriptRoot 'Target.cpp') "/Fo:$output/Target.obj" "/Fe:$output/EnhancedOwnedTarget.exe" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Owned target compilation failed.' }
    $targetHash = (Get-FileHash -LiteralPath "$output/EnhancedOwnedTarget.exe").Hash.ToLowerInvariant()
    @('#pragma once',"constexpr wchar_t kRepositoryRoot[]=L`"$($repo.Replace('\','\\'))`";",
        "constexpr char kHelperHash[]=`"$($receipt.helperSha256)`";","constexpr char kOwnedTargetHash[]=`"$targetHash`";") |
        Set-Content -LiteralPath "$output/BuildIdentity.h" -Encoding ascii
    Copy-Item -LiteralPath "$production/Bo3EnhancedHelper.dll" -Destination "$output/Bo3EnhancedHelper.dll"
    $sources = @((Join-Path $PSScriptRoot 'Runner.cpp'), (Join-Path $repo 'source/launch/enhanced/MappedHelper.cpp'),
        (Join-Path $repo 'source/launch/enhanced/SteamContext.cpp'),(Join-Path $repo 'source/launch/preentry/Identity.cpp'),
        (Join-Path $repo 'source/patches/vm_startup/PausedPatch.cpp'))
    & $compiler @flags @sources (Join-Path $DetoursRoot 'lib.X64/detours.lib') "/Fo:$output/" "/Fe:$output/EnhancedOwnedFixture.exe" /link bcrypt.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Owned mapping runner compilation failed.' }
    $results = @()
    foreach ($case in @('mapped','boot-invalid','code-invalid','unwind-invalid')) {
        & "$output/EnhancedOwnedFixture.exe" $case "$output/$case.json"
        if ($LASTEXITCODE -ne 0) { throw "Owned mapping case failed: $case" }
        $results += Get-Content -LiteralPath "$output/$case.json" -Raw | ConvertFrom-Json
    }
    # The production executable must reject this owned EXE before it creates any child.
    $refusal = & "$production/BO3-Enhanced-Zombies.exe" "$output/EnhancedOwnedTarget.exe" 2>&1
    if ($LASTEXITCODE -ne 2 -or "$refusal" -notmatch 'SHA256 differs') { throw 'Production identity refusal failed.' }
    @{passed=$true;productionIdentityRefusal=$true;helperSha256=$receipt.helperSha256;cases=$results;
        sourceHashes=@($sources + (Join-Path $PSScriptRoot 'Target.cpp') + $PSCommandPath | ForEach-Object { @{path=$_;sha256=(Get-FileHash -LiteralPath $_).Hash} })} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$output/result.json" -Encoding utf8
} finally { $env:INCLUDE = $savedInclude; $env:LIB = $savedLib }
