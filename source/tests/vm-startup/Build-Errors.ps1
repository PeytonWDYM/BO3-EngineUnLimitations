param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$output=[IO.Path]::GetFullPath($OutputDirectory)
function PhysicalPath([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path)
    $resolved=[IO.Path]::GetPathRoot($full)
    foreach($part in $full.Substring($resolved.Length).Split([char[]]@('\','/'),[StringSplitOptions]::RemoveEmptyEntries)) {
        $resolved=Join-Path $resolved $part
        if(Test-Path -LiteralPath $resolved) {
            $target=(Get-Item -LiteralPath $resolved).ResolveLinkTarget($true)
            if($target) { $resolved=$target.FullName }
        }
    }
    return $resolved
}
$repo=PhysicalPath $repo
$output=PhysicalPath $output
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep owned binaries outside the repository.' }
if(Test-Path -LiteralPath $output) { throw 'Use a new build directory.' }
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(!$installation) { throw 'Install the Visual C++ x64 build tools.' }
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE
$savedLib=$env:LIB
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    New-Item -ItemType Directory -Path $output | Out-Null
    @('#pragma once',"constexpr wchar_t kRepositoryRoot[]=L`"$($repo.Replace('\','\\'))`";") | Set-Content -LiteralPath (Join-Path $output 'BuildIdentity.h') -Encoding ascii
    $assembler=Join-Path $compilerRoot 'bin/Hostx64/x64/ml64.exe'
    foreach($file in @((Join-Path $repo 'source/patches/vm_startup/ErrorPrelude.asm'),(Join-Path $PSScriptRoot 'ErrorClear.asm'))) {
        $object=Join-Path $output ([IO.Path]::GetFileNameWithoutExtension($file)+'.obj')
        & $assembler /nologo /c "/Fo$object" $file
        if($LASTEXITCODE -ne 0) { throw 'Owned error assembly failed.' }
    }
    $compiler=Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    $sources=@((Join-Path $PSScriptRoot 'ErrorTarget.cpp'),(Join-Path $PSScriptRoot 'ErrorOwned.cpp'),(Join-Path $PSScriptRoot 'ErrorHooks.cpp'),
        (Join-Path $repo 'source/patches/vm_startup/StateErrors.cpp'),(Join-Path $repo 'source/launch/preentry/Identity.cpp'))
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 "/I$output" @sources "$output/ErrorPrelude.obj" "$output/ErrorClear.obj" "/Fo:$output/" "/Fe:$output/VmErrorFixture.exe" /link bcrypt.lib /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0) { throw 'Owned error fixture compilation failed.' }
    Get-FileHash -LiteralPath (Join-Path $output 'VmErrorFixture.exe') | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'build-hashes.json') -Encoding utf8
} finally { $env:INCLUDE=$savedInclude; $env:LIB=$savedLib }
