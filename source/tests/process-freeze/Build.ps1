#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[switch]$JobProof)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$output=[IO.Path]::GetFullPath($OutputDirectory)
if($output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or $output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private owned output.'}
New-Item -ItemType Directory -Path $output | Out-Null
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE;$savedLib=$env:LIB
$sources=@("$repo/source/launch/process_freeze/NativeState.cpp","$repo/source/launch/process_freeze/NativeJobFreeze.cpp","$PSScriptRoot/Target.cpp","$PSScriptRoot/Runner.cpp")
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    & (Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe') /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 @sources "/Fo:$output/" "/Fe:$output/ProcessFreezeProof.exe" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'Owned freeze compilation failed.'}
}finally{$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
$cases=@()
$caseNames=if($JobProof){@('job-explicit','job-future-bypass','job-primary','job-close-kill','job-refusals','job-death','job-death-bypass')}else{@('explicit','close','duplicate','nested','future','bypass','child-reference','refusals','target-exit','death-raw','death-safe-job-first','death-safe-state-first','prior-thread-suspend','primary-only')}
foreach($case in $caseNames) {
    & "$output/ProcessFreezeProof.exe" $case "$output/$case.json"
    if($LASTEXITCODE -ne 0){throw "Owned freeze case failed: $case"}
    $cases+=Get-Content "$output/$case.json" -Raw | ConvertFrom-Json
}
$repeatCases=if($JobProof){@('job-death','job-death-bypass')}else{@('death-raw','death-safe-job-first','death-safe-state-first')}
foreach($case in $repeatCases) {
    foreach($iteration in 2..8) {
        & "$output/ProcessFreezeProof.exe" $case "$output/$case-$iteration.json"
        if($LASTEXITCODE -ne 0){throw "Owned freeze repetition failed: $case $iteration"}
        $cases+=Get-Content "$output/$case-$iteration.json" -Raw | ConvertFrom-Json
    }
}
if(Get-Process ProcessFreezeProof -ErrorAction SilentlyContinue){throw 'An owned freeze fixture remains live.'}
$sourceFiles=@(Get-ChildItem "$repo/source/launch/process_freeze","$repo/source/tests/process-freeze" -File | Get-FileHash | Select-Object Path,Hash)
$nativeFiles=@('C:/Windows/System32/ntdll.dll','C:/Windows/System32/ntoskrnl.exe') | ForEach-Object {
    $file=Get-Item $_;@{path=$file.FullName;version=$file.VersionInfo.FileVersion;sha256=(Get-FileHash $_).Hash}
}
$snapshots=Join-Path $output 'source-snapshot'
New-Item -ItemType Directory -Path "$snapshots/launch","$snapshots/tests" | Out-Null
Copy-Item "$repo/source/launch/process_freeze/*" "$snapshots/launch"
Copy-Item "$repo/source/tests/process-freeze/*" "$snapshots/tests"
$limitations=if($JobProof){@('Owned target-routine counters do not prove arbitrary process quiescence.','Actual Steam upstream job restrictions and BO3 admission remain untested.')}else{@('Existing and future 0x40 bypass threads execute during process-state suspension.','Final state-reference close on controller death resumes a partial marker.')}
@{passed=$true;scope='Owned debugger-free native freeze proof only';mechanism=$(if($JobProof){'job-freeze'}else{'process-state'});allThreadQuiescenceProved=$false;
    limitations=$limitations;
    unexercised=@('Missing required export on this OS.','Actual Steam upstream job restrictions.');
    os=Get-ComputerInfo -Property OsName,OsVersion,OsBuildNumber;osBuild=Get-ItemProperty 'HKLM:/SOFTWARE/Microsoft/Windows NT/CurrentVersion' | Select-Object CurrentBuild,UBR;
    nativeFiles=$nativeFiles;sources=$sourceFiles;cases=$cases;artifacts=@(Get-ChildItem $output -File | Get-FileHash | Select-Object Path,Hash);
    sourceSnapshots=@(Get-ChildItem $snapshots -Recurse -File | Get-FileHash | Select-Object Path,Hash)} |
    ConvertTo-Json -Depth 10 | Set-Content "$output/result.json" -Encoding utf8
