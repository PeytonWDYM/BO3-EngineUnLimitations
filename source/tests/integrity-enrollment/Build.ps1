#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Python,[Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][string]$FrozenNativeBuild,[Parameter(Mandatory)][string]$DetoursRoot)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../launch/enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../../..');$output=PhysicalPath $OutputDirectory
if($output.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Use a new private enrollment output.'}
$native=PhysicalPath $FrozenNativeBuild
$prior=Get-Content (Join-Path $native 'result.json') -Raw | ConvertFrom-Json
if(!$prior.passed){throw 'Use a passing native owned build.'}
$frozenObjects=@(Get-ChildItem $native -Filter '*.obj' | Where-Object Name -notin @('Runner.obj','Coordinator.obj','Integration.obj'))
if(!$frozenObjects){throw 'The native serializer objects are missing.'}
$library=Join-Path $DetoursRoot 'lib.X64/detours.lib'
if((Get-FileHash $library).Hash -ne 'C2A9ED5D5B076D74EC50F1C4985056D0EF3421894C1BF59B66AE8A1D480724BC'){throw 'The pinned Detours library differs.'}
New-Item -ItemType Directory -Path $output | Out-Null
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compilerRoot=(Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=(Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$savedInclude=$env:INCLUDE;$savedLib=$env:LIB
try {
    $env:INCLUDE="$compilerRoot/include;$sdkRoot/Include/$sdk/um;$sdkRoot/Include/$sdk/shared;$sdkRoot/Include/$sdk/ucrt"
    $env:LIB="$compilerRoot/lib/x64;$sdkRoot/Lib/$sdk/um/x64;$sdkRoot/Lib/$sdk/ucrt/x64"
    $compiler=Join-Path $compilerRoot 'bin/Hostx64/x64/cl.exe'
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT /LD "$repo/source/tests/vm/EnhancedOverlayHelper.cpp" "/Fe:$output/Bo3EnhancedHelper.dll" "/Fo:$output/Helper.obj" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'The owned helper build failed.'}
    & $compiler /nologo /std:c++20 /EHsc /W4 /WX /MT "$PSScriptRoot/Target.cpp" "/Fe:$output/IntegrityEnrollmentFixture.exe" "/Fo:$output/Target.obj" /link /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'The owned target build failed.'}
    & $Python -B "$PSScriptRoot/Verify.py" --fixture "$output/IntegrityEnrollmentFixture.exe" --output $output --prepare-only
    if($LASTEXITCODE -ne 0){throw 'The authored inventory preparation failed.'}
    $identities=Get-Content "$output/fixture-identities.json" -Raw | ConvertFrom-Json
    Copy-Item -LiteralPath "$native/BuildIdentity.h" -Destination "$output/BuildIdentity.h"
    $identity=Get-Content "$output/BuildIdentity.h" -Raw
    foreach($field in @{kGameHash=$identities.fixtureSha256;kHelperHash=$identities.helperSha256;kGateHash=$identities.helperSha256;
        kIntegrityProfileId=$identities.profileDigests[0];kIntegrityOriginalDigest=$identities.profileDigests[1];kIntegrityReplacementDigest=$identities.profileDigests[2]}.GetEnumerator()){
        $identity=$identity -replace ('(?m)(constexpr char '+$field.Key+'\[\]=")[^"]+(";)'),('${1}'+$field.Value+'${2}')
    }
    [IO.File]::WriteAllText("$output/BuildIdentity.h",$identity)
    foreach($name in @('RuntimeUnwindProfile.h','GateWaitProfile.h','TargetExports.h','GameManifest.h','Profile.h')){Copy-Item -LiteralPath "$native/$name" -Destination $output}
    $flags=@('/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/O2','/Gy','/c','/DBO3_JOB_STARTUP','/DBO3_INTEGRITY_STARTUP',
        '/DBO3_JOB_OWNED_TEST','/DBO3_LATE_OWNED_TEST','/DBO3_INTEGRITY_OWNED_TEST','/DBO3_CODE_INTEGRITY_OWNED_TEST',
        "/I$output","/I$repo/source/launch/enhanced","/I$repo/source/patches/code_integrity","/I$DetoursRoot/include")
    & $compiler @flags "$repo/source/launch/job_startup/Coordinator.cpp" "$repo/source/launch/integrity_startup/Integration.cpp" "$PSScriptRoot/ReceiptTool.cpp" "/Fo:$output/"
    if($LASTEXITCODE -ne 0){throw 'The real native serializer compilation failed.'}
    $objects=@($frozenObjects.FullName)+@('Coordinator.obj','Integration.obj','ReceiptTool.obj' | ForEach-Object {Join-Path $output $_})
    & $compiler /nologo @objects $library "/Fe:$output/ReceiptTool.exe" /link bcrypt.lib shell32.lib ole32.lib dbghelp.lib /OPT:REF /INCREMENTAL:NO
    if($LASTEXITCODE -ne 0){throw 'The real native serializer link failed.'}
}finally{$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
& $Python -B "$PSScriptRoot/Verify.py" --fixture "$output/IntegrityEnrollmentFixture.exe" --output $output --receipt-tool "$output/ReceiptTool.exe"
if($LASTEXITCODE -ne 0){throw 'The read-only enrollment E2E failed.'}
$paths=@($frozenObjects.FullName)+@($library,"$repo/source/launch/job_startup/Coordinator.cpp","$repo/source/launch/integrity_startup/Integration.cpp")+
    @(Get-ChildItem $PSScriptRoot -File | ForEach-Object FullName)+@(Get-ChildItem $output -File | Where-Object Extension -in @('.h','.exe','.dll','.obj') | ForEach-Object FullName)
@{scope='Read-only owned native enrollment. Native success fields are authored, not a startup transaction.';
    files=@($paths | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 5 | Set-Content "$output/build-receipt.json" -Encoding utf8
