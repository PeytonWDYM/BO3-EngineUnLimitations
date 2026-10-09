param([Parameter(Mandatory)][string]$Python, [Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../../../scripts/release/Platform.ps1')
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$output = & $Python -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Resolve the fixture output directory.' }
if (Test-WithinPath $output $repo) { throw 'Keep owned artifacts outside the repository.' }
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory.' }
$msvc = Get-MsvcToolchain
$savedInclude = $env:INCLUDE
$savedLib = $env:LIB
try {
    New-Item -ItemType Directory -Path $output | Out-Null
    if ($msvc.Include) { $env:INCLUDE = $msvc.Include; $env:LIB = $msvc.Lib }
    $sources = @((Join-Path $PSScriptRoot 'AdmissionFixture.cpp'), (Join-Path $repo 'source/patches/vm_migration/Admission.cpp'))
    $assemblySources = @((Join-Path $repo 'source/patches/vm_migration/VersionGate.asm'), (Join-Path $repo 'source/patches/vm_migration/Reentries.asm'), (Join-Path $PSScriptRoot 'VersionBranchFixture.asm'))
    foreach ($assembly in $assemblySources) {
        & $msvc.Ml64 /nologo /c "/Fo$output/$([IO.Path]::GetFileNameWithoutExtension($assembly)).obj" $assembly
        if ($LASTEXITCODE -ne 0) { throw 'The migration version gate assembly failed.' }
    }
    $objects = @((Join-Path $output 'VersionGate.obj'), (Join-Path $output 'Reentries.obj'), (Join-Path $output 'VersionBranchFixture.obj'))
    $fixture = Join-Path $output 'AdmissionFixture.exe'
    & $msvc.Cl /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 @sources @objects "/Fo$output/" "/Fe$fixture" /link /INCREMENTAL:NO "/MAP:$output/AdmissionFixture.map"
    if ($LASTEXITCODE -ne 0) { throw 'The admission fixture build failed.' }
    Invoke-Windows $fixture | Tee-Object -FilePath (Join-Path $output 'trace.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The admission fixture failed.' }
    $exports = & $msvc.Dumpbin /exports $fixture | Out-String
    $exports | Set-Content (Join-Path $output 'exports.txt')
    foreach ($symbol in 'Bo3MigrationBindings', 'Bo3MigrationVersionBranches', 'Bo3MigrationLoadBindings', 'Bo3MigrationReentries', 'Bo3MigrationFlushBindings', 'LoadMigrationState', 'FlushMigrationState', 'MigrationFlushReentry', 'MigrationVersionGate', 'ReceiveMigrationHeader', 'ReceiveMigrationData', 'ReceiveMigrationHeaderAck', 'SendMigrationHeader', 'SendHeaderAck', 'CanLoadMigrationState') {
        if ($exports -notmatch "\s$symbol(?:\s|$)") { throw "Missing C export: $symbol" }
    }
    $symbols = & $msvc.Dumpbin /symbols (Join-Path $output 'Admission.obj') | Out-String
    $symbols | Set-Content (Join-Path $output 'object-symbols.txt')
    if ($symbols -match '\.CRT\$XCU|dynamic initializer|dynamic atexit') { throw 'Unexpected admission initializer.' }
    $seed = Join-Path $output 'original-sites.bin'
    & $Python -c 'import json,struct,sys; from pathlib import Path; core=json.loads(Path(sys.argv[1]).read_text()); migration=json.loads(Path(sys.argv[2]).read_text()); rows=[(r["rva"],r["original5"]) for r in core["nativeHooks"]]+[(r["rva"],r["original"]) for key in ("entryHooks","callHooks","branchHooks","immediateEdits") for r in migration[key]]; Path(sys.argv[3]).write_bytes(struct.pack("<I",len(rows))+b"".join(struct.pack("<II",rva,len(bytes.fromhex(value)))+bytes.fromhex(value) for rva,value in rows))' (Join-Path $repo 'source/patches/vm_pool/exact_build_inventory.json') (Join-Path $repo 'source/patches/vm_migration/exact_build_inventory.json') $seed
    if ($LASTEXITCODE -ne 0) { throw 'Cannot write the checked owned snapshot seed.' }
    $planSources = @((Join-Path $PSScriptRoot 'MigrationPlanFixture.cpp'), (Join-Path $repo 'source/patches/vm_migration/MigrationPlan.cpp'), (Join-Path $repo 'source/patches/vm_startup/NativePlan.cpp'), (Join-Path $repo 'source/patches/vm_startup/PausedPatch.cpp'))
    $planFixture = Join-Path $output 'MigrationPlanFixture.exe'
    & $msvc.Cl /nologo /std:c++20 /EHsc /W4 /WX /MT /O2 @planSources "/Fo$output/" "/Fe$planFixture" /link /INCREMENTAL:NO
    if ($LASTEXITCODE -ne 0) { throw 'The typed migration plan build failed.' }
    Invoke-Windows $planFixture $seed $output | Tee-Object -FilePath (Join-Path $output 'plan-trace.txt')
    if ($LASTEXITCODE -ne 0) { throw 'The composed migration plan fixture failed.' }
    if ((Get-FileHash (Join-Path $output 'before.bin')).Hash -ne (Get-FileHash (Join-Path $output 'restored.bin')).Hash) { throw 'The composed snapshot was not restored.' }
    $files = @($sources) + @($assemblySources) + @($planSources) + @($PSCommandPath, (Join-Path $PSScriptRoot 'failure-cases.txt'), (Join-Path $repo 'source/patches/vm_migration/exact_build_inventory.json'), (Join-Path $repo 'source/patches/vm_migration/Admission.h'), (Join-Path $repo 'source/patches/vm_migration/MigrationPlan.h'), $fixture, $planFixture, $seed, (Join-Path $output 'before.bin'), (Join-Path $output 'applied.bin'), (Join-Path $output 'restored.bin'), (Join-Path $output 'plan-addresses.txt'), (Join-Path $output 'plan-trace.txt'), (Join-Path $output 'trace.txt'), (Join-Path $output 'exports.txt'), (Join-Path $output 'object-symbols.txt'))
    $hashes = foreach ($file in $files) { Get-FileHash -LiteralPath $file -Algorithm SHA256 | Select-Object Path, Hash }
    @{passed = $true; files = @($hashes); scope = 'Owned callback admission, static Windows unwind, and composed core/migration real apply/rollback/removal E2E. No game, network, completed compressed whole-state load or deadline test.'} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $output 'result.json')
} finally { $env:INCLUDE = $savedInclude; $env:LIB = $savedLib }
