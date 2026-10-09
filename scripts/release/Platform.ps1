# Shared by the build and test scripts. Windows uses Visual Studio. Linux uses msvc-wine and Wine.

# Returns the x64 MSVC tools. Include and Lib stay empty on Linux because the msvc-wine wrappers set them.
function Get-MsvcToolchain {
    if ($IsWindows) {
        $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
        $installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if (!$installation) { throw 'Install Visual Studio C++ x64 build tools.' }
        $compilerRoot = (Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
        $sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
        $sdk = (Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
        $bin = Join-Path $compilerRoot 'bin/Hostx64/x64'
        return [pscustomobject]@{
            Cl = Join-Path $bin 'cl.exe'; Ml64 = Join-Path $bin 'ml64.exe'; Dumpbin = Join-Path $bin 'dumpbin.exe'
            Include = "$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
            Lib = "$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
        }
    }
    $root = if ($env:MSVC_ROOT) { $env:MSVC_ROOT } else { Join-Path $HOME 'msvc' }
    $bin = Join-Path $root 'bin/x64'
    if (!(Test-Path -LiteralPath (Join-Path $bin 'cl'))) { throw "Install msvc-wine into $root or set MSVC_ROOT." }
    return [pscustomobject]@{
        Cl = Join-Path $bin 'cl'; Ml64 = Join-Path $bin 'ml64'; Dumpbin = Join-Path $bin 'dumpbin'
        Include = $null; Lib = $null
    }
}

# Runs a Windows program directly on Windows and through Wine elsewhere. Set WINE to choose the Wine binary.
# Uses $args so that options such as -m reach the program unchanged.
function Invoke-Windows {
    $program = $args[0]
    $arguments = @($args | Select-Object -Skip 1)
    if ($IsWindows) { & $program @arguments; return }
    $wine = if ($env:WINE) { $env:WINE } else { 'wine' }
    if (!(Get-Command $wine -ErrorAction SilentlyContinue)) { throw 'Install Wine or set WINE to a Wine binary.' }
    & $wine $program @arguments
}

# True when Path is Root or lies below it.
function Test-WithinPath([string]$Path, [string]$Root) {
    $separator = [IO.Path]::DirectorySeparatorChar
    $Root = $Root.TrimEnd($separator)
    return $Path.Equals($Root, [StringComparison]::OrdinalIgnoreCase) -or
        $Path.StartsWith($Root + $separator, [StringComparison]::OrdinalIgnoreCase)
}
