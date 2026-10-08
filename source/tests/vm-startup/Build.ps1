param([Parameter(Mandatory)][string]$OutputDirectory, [string]$DetoursRoot, [switch]$NativeComposition)
$ErrorActionPreference = 'Stop'
function PhysicalPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $resolved = [IO.Path]::GetPathRoot($full)
    foreach ($part in $full.Substring($resolved.Length).Split([char[]]@('\', '/'), [StringSplitOptions]::RemoveEmptyEntries)) {
        $resolved = Join-Path $resolved $part
        if (Test-Path -LiteralPath $resolved) {
            $target = (Get-Item -LiteralPath $resolved).ResolveLinkTarget($true)
            if ($target) { $resolved = $target.FullName }
        }
    }
    return $resolved
}
$repo = PhysicalPath (Join-Path $PSScriptRoot '../../..')
$output = PhysicalPath $OutputDirectory
if ($output.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep owned binaries outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Use a new build directory.' }
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
    $compiler = Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    $flags = @('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2',"/I$output")
    $targetLibraries = @()
    $runnerLibraries = @()
    if ($DetoursRoot) {
        $DetoursRoot = PhysicalPath $DetoursRoot
        if ((& git -C $DetoursRoot rev-parse HEAD) -ne 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833' -or
            (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
            (& git -C $DetoursRoot status --porcelain --untracked-files=no)) { throw 'Use unchanged official Detours v4.0.1.' }
        $flags += @('/DVM_STARTUP_COMPOSED',"/I$DetoursRoot/include")
        $detoursLibrary = Join-Path $DetoursRoot 'lib.X64/detours.lib'
        if (!(Test-Path -LiteralPath $detoursLibrary)) { throw 'Use the existing pinned x64 Detours library.' }
        & $compiler @flags /LD (Join-Path $PSScriptRoot 'Consumer.cpp') "/Fe:$output/VmStartupConsumer.dll" "/Fo:$output/Consumer.obj" /link /INCREMENTAL:NO
        if ($LASTEXITCODE -ne 0) { throw 'Owned imported consumer compilation failed.' }
        $targetLibraries += "$output/VmStartupConsumer.lib"
        $helperSources = @((Join-Path $PSScriptRoot 'Helper.cpp'),(Join-Path $repo 'source/patches/vm_pool/StateAdapter.cpp'),(Join-Path $repo 'source/patches/vm_pool/NativeStateBridge.cpp'))
        $helperSources += (Join-Path $repo 'source/patches/vm_startup/StateErrors.cpp')
        $assembler=Join-Path $compilerRoot 'bin/Hostx64/x64/ml64.exe'
        $helperObjects=@()
        foreach($name in @('ErrorPrelude','OriginalEntries')) {
            $object=Join-Path $output "$name.obj"
            & $assembler /nologo /c "/Fo$object" (Join-Path $repo "source/patches/vm_startup/$name.asm")
            if($LASTEXITCODE -ne 0) { throw 'Static helper thunk assembly failed.' }
            $helperObjects += $object
        }
        & $compiler @flags /LD @helperSources @helperObjects $detoursLibrary "/Fe:$output/VmStartupHelper.dll" "/Fo:$output/" /link "/DEF:$PSScriptRoot/Helper.def" /INCREMENTAL:NO
        if ($LASTEXITCODE -ne 0) { throw 'Owned pre-imported helper compilation failed.' }
        $runnerLibraries += $detoursLibrary
        Copy-Item -LiteralPath (Join-Path $DetoursRoot 'LICENSE.md') -Destination (Join-Path $output 'Detours-LICENSE.md')
        @{ commit='e4bfd6b03e50de46b47abfbd1e46b384f0c5f833'; librarySha256=(Get-FileHash -LiteralPath $detoursLibrary).Hash;
            sourceRoot=$DetoursRoot } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'detours-provenance.json') -Encoding utf8
    }
    & $compiler @flags (Join-Path $PSScriptRoot 'Target.cpp') @targetLibraries "/Fe:$output/VmStartupTarget.exe" "/Fo:$output/Target.obj" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Owned target compilation failed.' }
    $hash = (Get-FileHash -LiteralPath (Join-Path $output 'VmStartupTarget.exe')).Hash.ToLowerInvariant()
    $identity = @('#pragma once', "constexpr wchar_t kRepositoryRoot[]=L`"$($repo.Replace('\','\\'))`";", "constexpr char kTargetHash[]=`"$hash`";")
    if ($DetoursRoot) {
        foreach($file in @('Helper','Consumer')) {
            $fileHash=(Get-FileHash -LiteralPath (Join-Path $output "VmStartup$file.dll")).Hash.ToLowerInvariant()
            $identity += "constexpr char k$($file)Hash[]=`"$fileHash`";"
        }
    }
    $identity |
        Set-Content -LiteralPath (Join-Path $output 'BuildIdentity.h') -Encoding ascii
    $sources = @((Join-Path $PSScriptRoot 'Runner.cpp'), (Join-Path $repo 'source/patches/vm_startup/DebugGate.cpp'),
        (Join-Path $repo 'source/patches/vm_startup/PausedPatch.cpp'), (Join-Path $repo 'source/launch/preentry/Identity.cpp'))
    if ($DetoursRoot) { $sources += (Join-Path $PSScriptRoot 'ComposedPlan.cpp') }
    & $compiler @flags @sources @runnerLibraries "/Fe:$output/VmStartupFixture.exe" "/Fo:$output/" /link bcrypt.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Owned gate compilation failed.' }
    if($NativeComposition) {
        if(!$DetoursRoot) { throw 'Native composition requires the pinned pre-import helper.' }
        & $assembler /nologo /c "/Fo$output/NativeContinuations.obj" (Join-Path $PSScriptRoot 'NativeContinuations.asm')
        if($LASTEXITCODE -ne 0) { throw 'Owned native continuation assembly failed.' }
        $nativeSources=@((Join-Path $PSScriptRoot 'NativeTarget.cpp'),(Join-Path $PSScriptRoot 'NativeOwned.cpp'),(Join-Path $repo 'source/launch/preentry/Identity.cpp'))
        & $compiler @flags @nativeSources "$output/NativeContinuations.obj" "$output/VmStartupConsumer.lib" "/Fo:$output/" "/Fe:$output/VmNativeTarget.exe" /link bcrypt.lib /INCREMENTAL:NO
        if($LASTEXITCODE -ne 0) { throw 'Owned native target compilation failed.' }
        $nativeHash=(Get-FileHash -LiteralPath (Join-Path $output 'VmNativeTarget.exe')).Hash.ToLowerInvariant()
        "constexpr char kNativeTargetHash[]=`"$nativeHash`";" | Add-Content -LiteralPath (Join-Path $output 'BuildIdentity.h') -Encoding ascii
        $nativeSources=@((Join-Path $PSScriptRoot 'NativeRunner.cpp'),(Join-Path $repo 'source/patches/vm_startup/DebugGate.cpp'),
            (Join-Path $repo 'source/patches/vm_startup/PausedPatch.cpp'),(Join-Path $repo 'source/patches/vm_startup/NativePlan.cpp'),
            (Join-Path $repo 'source/patches/vm_startup/NearRelay.cpp'),(Join-Path $repo 'source/launch/preentry/Identity.cpp'))
        & $compiler @flags @nativeSources $detoursLibrary "/Fo:$output/" "/Fe:$output/VmNativeFixture.exe" /link bcrypt.lib /INCREMENTAL:NO
        if($LASTEXITCODE -ne 0) { throw 'Owned native composition runner compilation failed.' }
    }
    Get-FileHash -LiteralPath (Join-Path $output 'VmStartupTarget.exe'),(Join-Path $output 'VmStartupFixture.exe') | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $output 'build-hashes.json') -Encoding utf8
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
