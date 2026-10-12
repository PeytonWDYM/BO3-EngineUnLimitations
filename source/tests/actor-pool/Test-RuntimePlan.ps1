#Requires -Version 7.0
[CmdletBinding(DefaultParameterSetName='Runtime')]
param([Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory,ParameterSetName='Runtime')][string]$Seed,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory,ParameterSetName='SourceClosure')][switch]$SourceClosureOnly)
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($Output)
$lab=[IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.codex/labs/bo3-engine'))
if (-not $target.StartsWith($lab+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $target)) {throw 'Use a new private BO3 lab directory.'}
New-Item -ItemType Directory -Path $target | Out-Null
$patches=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../patches/actor_pool'))
$generated=Join-Path $target 'RuntimeProfile.generated.h'
& $Python -B (Join-Path $patches 'Generate-RuntimeProfile.py') --output $generated
if ($LASTEXITCODE -ne 0) {throw 'The runtime profile generation failed.'}
$repeated=Join-Path $target 'RuntimeProfile.repeated.h'
& $Python -B (Join-Path $patches 'Generate-RuntimeProfile.py') --output $repeated
if ($LASTEXITCODE -ne 0 -or (Get-FileHash -LiteralPath $generated).Hash -ne (Get-FileHash -LiteralPath $repeated).Hash) {throw 'The runtime profile is not reproducible.'}
$inventory=Get-Content -LiteralPath (Join-Path $patches 'runtime_inventory.json') -Raw | ConvertFrom-Json
$closureNames=@($inventory.source_sha256.PSObject.Properties.Name)+@('runtime_inventory.json')
$closureHeaders=@()
foreach($lineEnding in @('LF','CRLF')) {
    $closureRoot=Join-Path $target "closure-$lineEnding"
    New-Item -ItemType Directory -Path $closureRoot | Out-Null
    foreach($name in $closureNames) {
        $sourceText=[IO.File]::ReadAllText((Join-Path $patches $name)).Replace("`r`n","`n")
        if($lineEnding -eq 'CRLF') {$sourceText=$sourceText.Replace("`n","`r`n")}
        [IO.File]::WriteAllText((Join-Path $closureRoot $name),$sourceText,[Text.UTF8Encoding]::new($false))
    }
    $closureHeader=Join-Path $closureRoot 'RuntimeProfile.generated.h'
    & $Python -B (Join-Path $closureRoot 'Generate-RuntimeProfile.py') --output $closureHeader
    if($LASTEXITCODE -ne 0) {throw 'The runtime source closure depends on source line endings.'}
    if((Get-FileHash -LiteralPath $closureHeader).Hash -ne (Get-FileHash -LiteralPath $generated).Hash) {throw 'The runtime header differs across source line endings.'}
    $closureHeaders+=$closureHeader
}
$changedSource=Join-Path (Join-Path $target 'closure-LF') 'table_plan.py'
[IO.File]::AppendAllText($changedSource,"`n# A material source change.`n",[Text.UTF8Encoding]::new($false))
& $Python -B (Join-Path (Join-Path $target 'closure-LF') 'Generate-RuntimeProfile.py') --output (Join-Path $target 'changed-source-refused.h') 2>&1 | Set-Content -LiteralPath (Join-Path $target 'source-change-refusal.txt')
if($LASTEXITCODE -eq 0) {throw 'The runtime source closure admitted a material source change.'}
if($SourceClosureOnly) {
    $paths=@($PSCommandPath,$generated,$repeated,(Join-Path $patches 'Generate-RuntimeProfile.py'),(Join-Path $patches 'runtime_inventory.json'))+$closureHeaders
    @{passed=$true;sourceClosureLineEndings=@('LF','CRLF');materialSourceChangeRefused=$true;scope='Runtime source closure and generated header reproduce without private game inputs.';files=@($paths | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
    return
}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler=Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdk=Get-ChildItem (Join-Path $sdkRoot 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$savedInclude,$savedLib=$env:INCLUDE,$env:LIB
try {
    $env:INCLUDE="$target;$($compiler.FullName)/include;$sdkRoot/Include/$($sdk.Name)/um;$sdkRoot/Include/$($sdk.Name)/shared;$sdkRoot/Include/$($sdk.Name)/ucrt"
    $env:LIB="$($compiler.FullName)/lib/x64;$sdkRoot/Lib/$($sdk.Name)/um/x64;$sdkRoot/Lib/$($sdk.Name)/ucrt/x64"
    $fixture=Join-Path $PSScriptRoot 'RuntimePlanFixture.cpp'
    $implementation=Join-Path $patches 'RuntimePlan.cpp'
    $arena=Join-Path $patches 'ActorArena.cpp'
    $transaction=Join-Path $patches '../vm_startup/PausedPatch.cpp'
    $binary=Join-Path $target 'RuntimePlanFixture.exe'
    & (Join-Path $compiler.FullName 'bin/Hostx64/x64/cl.exe') /nologo /EHsc /W4 /WX /MT /std:c++20 /O2 $fixture $implementation $arena $transaction "/Fe:$binary" "/Fo:$target/" /link bcrypt.lib /INCREMENTAL:NO /Brepro 2>&1 | Tee-Object -FilePath (Join-Path $target 'build.txt')
    if ($LASTEXITCODE -ne 0) {throw 'The actor runtime plan build failed.'}
    & $binary $Seed (Join-Path $target 'result.json')
    if ($LASTEXITCODE -ne 0) {throw 'The owned actor runtime plan failed.'}
    & $binary $Seed (Join-Path $target 'result-low.json') '0x180000000'
    if ($LASTEXITCODE -ne 0) {throw 'The low-address actor runtime plan failed.'}
    & $binary $Seed (Join-Path $target 'result-high.json') '0x300000000'
    if ($LASTEXITCODE -ne 0) {throw 'The high-address actor runtime plan failed.'}
    $paths=@($fixture,$implementation,$arena,$transaction,$PSCommandPath,$generated,$binary,$Seed)+$closureHeaders+@(
        (Join-Path $target 'result.json'),(Join-Path $target 'result-low.json'),(Join-Path $target 'result-high.json'),
        (Join-Path $patches 'RuntimePlan.h'),(Join-Path $patches 'ActorArena.h'),(Join-Path $patches 'ActorRecord.h'),
        (Join-Path $patches 'NativeLoadBridge.h'),(Join-Path $patches 'RuntimeBinding.h'),(Join-Path $patches 'LoadContext.h'),
        (Join-Path $patches 'runtime_inventory.json'),(Join-Path $patches 'Generate-RuntimeProfile.py'))
    @{passed=$true;sourceClosureLineEndings=@('LF','CRLF');materialSourceChangeRefused=$true;scope='Owned Windows runtime preparation, publication, registration, rollback, commit, and exact guard refusal. Game compatibility requires separate checks.';files=@($paths | Get-FileHash | Select-Object Path,Hash)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'receipt.json')
}finally {$env:INCLUDE=$savedInclude;$env:LIB=$savedLib}
