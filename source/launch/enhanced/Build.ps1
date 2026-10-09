param([Parameter(Mandatory)][string]$OutputDirectory, [Parameter(Mandatory)][string]$DetoursRoot,
    [Parameter(Mandatory)][string]$Python)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'PhysicalPath.ps1')
$repo = PhysicalPath (Join-Path $PSScriptRoot '../../..')
$output = PhysicalPath $OutputDirectory
if ($output.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep generated binaries outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Use a new build directory.' }
$DetoursRoot = PhysicalPath $DetoursRoot
if ((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no)) { throw 'Use unchanged official Detours v4.0.1.' }
$detoursLibrary = Join-Path $DetoursRoot 'lib.X64/detours.lib'
if ((Get-FileHash -LiteralPath $detoursLibrary).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC') {
    throw 'The pinned x64 Detours library differs.'
}
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) { throw 'Install the Visual C++ x64 build tools.' }
$compilerRoot = (Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk = (Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
try {
    $env:INCLUDE = "$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    New-Item -ItemType Directory -Path $output | Out-Null
    & $Python (Join-Path $PSScriptRoot 'Merge-Inventory.py') --vm (Join-Path $repo 'source/patches/vm_pool/exact_build_inventory.json') --migration (Join-Path $repo 'source/patches/vm_migration/exact_build_inventory.json') --output "$output/merged-inventory.json"
    if ($LASTEXITCODE -ne 0) { throw 'Native inventory merge failed.' }
    & $Python (Join-Path $PSScriptRoot 'Generate-GameProfile.py') --inventory "$output/merged-inventory.json" --output "$output/GameManifest.h"
    if ($LASTEXITCODE -ne 0) { throw 'Native game profile generation failed.' }
    $compiler = Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    $assembler = Join-Path $compilerRoot 'bin/Hostx64/x64/ml64.exe'
    $flags = @('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2',"/I$output", "/I$PSScriptRoot", "/I$DetoursRoot/include")
    $objects = @()
    foreach ($relative in @('vm_startup/ErrorPrelude','vm_startup/OriginalEntries','vm_migration/VersionGate','vm_migration/Reentries')) {
        $object = Join-Path $output (($relative.Replace('/', '-')) + '.obj')
        & $assembler /nologo /c "/Fo$object" (Join-Path $repo "source/patches/$relative.asm")
        if ($LASTEXITCODE -ne 0) { throw 'Enhanced helper assembly failed.' }
        $objects += $object
    }
    $helperSources = @((Join-Path $PSScriptRoot 'Helper.cpp'))
    foreach ($relative in @('vm_pool/StateAdapter','vm_pool/NativeStateBridge','vm_startup/StateErrors','vm_migration/Admission')) {
        $helperSources += Join-Path $repo "source/patches/$relative.cpp"
    }
    & $compiler @flags /LD @helperSources @objects $detoursLibrary "/Fo:$output/" "/Fe:$output/Bo3EnhancedHelper.dll" /link "/DEF:$PSScriptRoot/Helper.def" /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Enhanced helper compilation failed.' }
    $helperHash = (Get-FileHash -LiteralPath "$output/Bo3EnhancedHelper.dll").Hash.ToLowerInvariant()
    @('#pragma once', 'constexpr wchar_t kRepositoryRoot[]=L".";',
        'constexpr char kGameHash[]="0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0";',
        "constexpr char kHelperHash[]=`"$helperHash`";") | Set-Content -LiteralPath "$output/BuildIdentity.h" -Encoding ascii
    $parentSources = @()
    foreach ($file in @('Launcher','MappedHelper','SessionReceipt','GameProfile','SteamContext')) { $parentSources += Join-Path $PSScriptRoot "$file.cpp" }
    foreach ($relative in @('vm_startup/DebugGate','vm_startup/PausedPatch','vm_startup/NativePlan','vm_startup/NearRelay','vm_migration/MigrationPlan')) {
        $parentSources += Join-Path $repo "source/patches/$relative.cpp"
    }
    $parentSources += Join-Path $repo 'source/launch/preentry/Identity.cpp'
    & $compiler @flags @parentSources $detoursLibrary "/Fo:$output/" "/Fe:$output/BO3-Enhanced-Zombies.exe" /link bcrypt.lib shell32.lib ole32.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Enhanced launcher compilation failed.' }
    Copy-Item -LiteralPath (Join-Path $DetoursRoot 'LICENSE.md') -Destination "$output/Detours-LICENSE.md"
    $sourcePaths = @($helperSources + $parentSources + (Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName))
    foreach ($folder in @('vm_pool','vm_startup','vm_migration')) {
        $sourcePaths += Get-ChildItem (Join-Path $repo "source/patches/$folder") -File | Where-Object Extension -in @('.h','.asm','.json') | ForEach-Object FullName
    }
    $sourcePaths += Join-Path $repo 'source/launch/preentry/Identity.h'
    $sourcePaths += @("$output/GameManifest.h", "$output/BuildIdentity.h", "$output/merged-inventory.json")
    $sourcePaths = $sourcePaths | Sort-Object -Unique
    $sources = @($sourcePaths | ForEach-Object { @{path=$_;sha256=(Get-FileHash -LiteralPath $_).Hash} })
    @{candidate='0.1.0-test.3';status='experimental-unvalidated-game';serverTotal=500001;clientRoots=18;migrationBufferBytes=33554432;
        detoursCommit='e4bfd6b03e50de46b47abfbd1e46b384f0c5f833';detoursLibrarySha256=(Get-FileHash -LiteralPath $detoursLibrary).Hash;
        helperSha256=$helperHash;launcherSha256=(Get-FileHash -LiteralPath "$output/BO3-Enhanced-Zombies.exe").Hash;sources=$sources} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$output/build-receipt.json" -Encoding utf8
} finally { $env:INCLUDE = $savedInclude; $env:LIB = $savedLib }
