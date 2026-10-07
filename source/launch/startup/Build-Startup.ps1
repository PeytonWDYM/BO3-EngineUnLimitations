param([Parameter(Mandatory)][string]$DetoursRoot, [Parameter(Mandatory)][string]$OutputDirectory)
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
    throw 'Keep build output outside the repository.'
}
$DetoursRoot = PhysicalPath $DetoursRoot
foreach ($path in @($output, $DetoursRoot)) {
    if ($path.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or $path.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Keep build output and Detours source outside the repository.'
    }
}
if (Test-Path -LiteralPath $output) { throw 'Use a new build directory.' }
$commit = 'e4bfd6b03e50de46b47abfbd1e46b384f0c5f833'
if ((& git -C $DetoursRoot rev-parse HEAD) -ne $commit -or
    (& git -C $DetoursRoot remote get-url origin) -ne 'https://github.com/microsoft/Detours.git' -or
    (& git -C $DetoursRoot status --porcelain --untracked-files=no)) {
    throw 'Use the unchanged official Detours v4.0.1 commit.'
}
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) { throw 'Install the Visual C++ x64 build tools.' }
$compilerRoot = (Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk = (Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
$savedPath = $env:PATH
try {
    $env:INCLUDE = "$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt;$sdkRoot/Include/$sdk/winrt"
    $env:LIB = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $env:PATH = "$compilerRoot/bin/Hostx64/x64;$env:PATH"
    $compiler = Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    New-Item -ItemType Directory -Path $output | Out-Null
    $dependencyCopy = Join-Path $output 'dependency/Detours'
    New-Item -ItemType Directory -Path (Split-Path $dependencyCopy) | Out-Null
    Copy-Item -LiteralPath $DetoursRoot -Destination $dependencyCopy -Recurse
    $DetoursRoot = $dependencyCopy
    Push-Location (Join-Path $DetoursRoot 'src')
    try { & (Join-Path $compilerRoot 'bin/Hostx64/x64/nmake.exe') /nologo /A DETOURS_TARGET_PROCESSOR=X64
        if ($LASTEXITCODE -ne 0) { throw 'The pinned Detours build failed.' }
    } finally { Pop-Location }
    $tests = Join-Path $repo 'source/tests/startup'
    $flags = @('/nologo', '/std:c++17', '/EHsc', '/W4', '/WX', '/MT', '/Od', "/I$tests", "/I$DetoursRoot/include", "/I$output")
    & $compiler @flags /LD (Join-Path $tests 'FactoryShim.cpp') (Join-Path $tests 'WorkerConsumer.cpp') "/Fe:$output/StartupFactories.dll" "/Fo:$output/" /link "/DEF:$tests/FactoryShim.def" uuid.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The provider build failed.' }
    & $compiler @flags /LD (Join-Path $tests 'ImportedConsumer.cpp') "$output/StartupFactories.lib" "/Fe:$output/StartupConsumer.dll" "/Fo:$output/ImportedConsumer.obj" /link uuid.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The imported consumer build failed.' }
    & $compiler @flags (Join-Path $tests 'Target.cpp') "$output/StartupFactories.lib" "$output/StartupConsumer.lib" "/Fe:$output/StartupTarget.exe" "/Fo:$output/Target.obj" /link uuid.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The target build failed.' }
    $helperSources = @('Helper.cpp', 'RuntimeOwner.cpp', 'Stop.cpp', 'ThreadGate.cpp') | ForEach-Object { Join-Path $PSScriptRoot $_ }
    $helperSources += Join-Path $tests 'Consumers.cpp'
    $helperSources += @('ProviderRoots.cpp', 'ProviderAudio.cpp', 'ProviderDirectSound.cpp') | ForEach-Object { Join-Path $repo "source/tests/activation/$_" }
    $helperSources += @('RenderSink.cpp', 'SoundSink.cpp', 'Report.cpp') | ForEach-Object { Join-Path $repo "source/tests/quiet/$_" }
    $helperSources += Get-ChildItem (Join-Path $repo 'source/launch/activation') -Filter *.cpp | ForEach-Object FullName
    $helperSources += Get-ChildItem (Join-Path $repo 'source/launch/quiet') -Filter *.cpp | ForEach-Object FullName
    & $compiler @flags /LD @helperSources "$output/StartupFactories.lib" "$DetoursRoot/lib.X64/detours.lib" "/Fe:$output/StartupHelper64.dll" "/Fo:$output/" /link "/DEF:$PSScriptRoot/Helper.def" ole32.lib uuid.lib dxguid.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The helper build failed.' }
    $identity = @('#pragma once', "constexpr wchar_t kRepositoryRoot[] = L`"$($repo.Replace('\', '\\'))`";")
    foreach ($item in @(@('Target', 'exe'), @('Factories', 'dll'), @('Consumer', 'dll'), @('Helper64', 'dll'))) {
        $hash = (Get-FileHash -LiteralPath "$output/Startup$($item[0]).$($item[1])" -Algorithm SHA256).Hash.ToLowerInvariant()
        $name = if ($item[0] -eq 'Helper64') { 'Helper' } elseif ($item[0] -eq 'Factories') { 'Provider' } else { $item[0] }
        $identity += "constexpr char k$($name)Hash[] = `"$hash`";"
    }
    $identity | Set-Content -LiteralPath (Join-Path $output 'BuildIdentity.h') -Encoding ascii
    & $compiler @flags (Join-Path $PSScriptRoot 'Launcher.cpp') (Join-Path $PSScriptRoot '../preentry/Identity.cpp') "$DetoursRoot/lib.X64/detours.lib" "/Fe:$output/StartupLauncher.exe" "/Fo:$output/" /link bcrypt.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The launcher build failed.' }
    Copy-Item -LiteralPath (Join-Path $DetoursRoot 'LICENSE.md') -Destination (Join-Path $output 'Detours-LICENSE.md')
    @{ repository = 'https://github.com/microsoft/Detours.git'; commit = $commit;
       licenseSha256 = (Get-FileHash -LiteralPath (Join-Path $DetoursRoot 'LICENSE.md')).Hash.ToLowerInvariant();
       librarySha256 = (Get-FileHash -LiteralPath (Join-Path $DetoursRoot 'lib.X64/detours.lib')).Hash.ToLowerInvariant() } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'detours-provenance.json') -Encoding utf8
} finally { $env:INCLUDE = $savedInclude; $env:LIB = $savedLib; $env:PATH = $savedPath }
