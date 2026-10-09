param([Parameter(Mandatory)][string]$OutputDirectory, [Parameter(Mandatory)][string]$Python)
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
    throw 'Keep admission binaries outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Use a new build directory.' }
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
    & $Python (Join-Path $repo 'source/launch/enhanced/Generate-GameProfile.py') --inventory (Join-Path $repo 'source/patches/vm_pool/exact_build_inventory.json') --output (Join-Path $output 'GameManifest.h')
    if ($LASTEXITCODE -ne 0) { throw 'Exact game metadata generation failed.' }
    $compiler = Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    $flags = @('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2',"/I$output", "/I$repo/source/launch/enhanced")
    & $compiler @flags /LD (Join-Path $PSScriptRoot 'GameAdmissionShim.cpp') (Join-Path $repo 'source/launch/enhanced/GameProfile.cpp') (Join-Path $repo 'source/patches/vm_startup/PausedPatch.cpp') "/Fo:$output/" "/Fe:$output/GameAdmission.dll" /link bcrypt.lib /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'Owned game admission compilation failed.' }
} finally { $env:INCLUDE = $savedInclude; $env:LIB = $savedLib }
