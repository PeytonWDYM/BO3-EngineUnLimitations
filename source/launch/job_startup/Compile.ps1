# Dot-source only after the caller admits a new private output directory and pinned Detours.
function Compile-JobStartup([string]$Repo,[string]$Output,[string]$DetoursRoot,[switch]$Owned) {
    $vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    $installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    $compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
    $sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
    $sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
    $savedInclude=$env:INCLUDE;$savedLib=$env:LIB
    try {
        $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
        $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
        $sources=@('OwnedChild','MappedGate','FixedPlan','PrivateReceipt') | ForEach-Object {Join-Path $Repo "source/launch/late_startup/$_.cpp"}
        $sources+=@('Coordinator','OwnedJob','PrimaryAdmission','RuntimeUnwind') | ForEach-Object {Join-Path $Repo "source/launch/job_startup/$_.cpp"}
        $sources+=@('NativeJobFreeze','NativeState') | ForEach-Object {Join-Path $Repo "source/launch/process_freeze/$_.cpp"}
        $sources+=@('MappedHelper','GameProfile','SteamContext') | ForEach-Object {Join-Path $Repo "source/launch/enhanced/$_.cpp"}
        $sources+=Join-Path $Repo 'source/launch/preentry/Identity.cpp'
        $sources+=@('vm_startup/PausedPatch','vm_startup/NativePlan','vm_startup/NearRelay','vm_migration/MigrationPlan') | ForEach-Object {Join-Path $Repo "source/patches/$_.cpp"}
        $entry=if($Owned){'source/tests/job-startup/Runner.cpp'}else{'source/launch/job_startup/Launcher.cpp'}
        $sources+=Join-Path $Repo $entry
        if($Owned){$sources+=@('SerialLoader','ParentDeath') | ForEach-Object {Join-Path $Repo "source/tests/job-startup/$_.cpp"}}

        $flags=@('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2','/Gy','/MP4','/DBO3_JOB_STARTUP',"/I$Output","/I$Repo/source/launch/enhanced","/I$DetoursRoot/include")
        if($Owned){$flags+=@('/DBO3_LATE_OWNED_TEST','/DBO3_JOB_OWNED_TEST')}
        $name=if($Owned){'JobStartupOwnedFixture.exe'}else{'BO3-Job-Zombies.exe'}
        & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') @flags @sources (Join-Path $DetoursRoot 'lib.X64/detours.lib') "/Fo:$Output/" "/Fe:$Output/$name" /link bcrypt.lib shell32.lib ole32.lib dbghelp.lib /OPT:REF /INCREMENTAL:NO | Out-Host
        if($LASTEXITCODE -ne 0){throw 'Job coordinator compilation failed.'}
        return $sources
    }finally{$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
}
