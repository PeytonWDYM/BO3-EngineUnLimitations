# Dot-source after admitting a new private output and pinned Detours.
function Compile-PassiveControl([string]$Repo,[string]$Output,[string]$DetoursRoot,[switch]$Owned) {
    $vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    $installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    $compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
    $sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
    $sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
    $savedInclude=$env:INCLUDE;$savedLib=$env:LIB
    try {
        $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
        $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
        $sources=@('OwnedChild','MappedGate','PassiveControl','ControlAdmission','PrivateReceipt') | ForEach-Object {Join-Path $Repo "source/launch/late_startup/$_.cpp"}
        $sources+=@('MappedHelper','GameProfile','SteamContext') | ForEach-Object {Join-Path $Repo "source/launch/enhanced/$_.cpp"}
        $sources+=Join-Path $Repo 'source/launch/preentry/Identity.cpp'
        $sources+=Join-Path $Repo 'source/launch/late_startup/PassiveControlRead.cpp'
        $sources+=Join-Path $Repo $(if($Owned){'source/tests/late-startup/PassiveControlRunner.cpp'}else{'source/launch/late_startup/PassiveControlLauncher.cpp'})
        $flags=@('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2','/DBO3_LATE_STOCK_CONTROL','/DBO3_LATE_PASSIVE_CONTROL',"/I$Output","/I$Repo/source/launch/enhanced","/I$DetoursRoot/include")
        if($Owned){$flags+='/DBO3_LATE_OWNED_TEST'}
        $name=if($Owned){'PassiveControlOwnedFixture.exe'}else{'BO3-Late-Passive-Control.exe'}
        & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') @flags @sources (Join-Path $DetoursRoot 'lib.X64/detours.lib') "/Fo:$Output/" "/Fe:$Output/$name" /link bcrypt.lib shell32.lib ole32.lib /INCREMENTAL:NO | Out-Host
        if($LASTEXITCODE -ne 0){throw 'Late control compilation failed.'}
        return $sources
    }finally{$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
}
