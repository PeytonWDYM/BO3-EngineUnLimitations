[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$GhidraDirectory,
    [Parameter(Mandatory)][string]$JavaHome,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\','/')
if ($output -eq $repo -or $output.StartsWith($repo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Write Ghidra artifacts outside the repository.'
}
if (Test-Path -LiteralPath $output) { throw 'Choose a new E2E output directory.' }
New-Item -ItemType Directory -Path $output -Force | Out-Null
& (Join-Path $repo 'source/launch/Build-Tools.ps1') -OutputDirectory (Join-Path $output 'bin')
$fixture = Join-Path $output 'bin/GhidraFixture.exe'
$target = Start-Process -FilePath $fixture -ArgumentList hold -WindowStyle Hidden -PassThru
[PSCustomObject]@{
    pid=$target.Id
    startedUtc=$target.StartTime.ToUniversalTime().ToString('o')
    sha256=(Get-FileHash -LiteralPath $fixture -Algorithm SHA256).Hash
    executable=$fixture
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'identity.json') -Encoding utf8
$dumpJob = $null
try {
    Import-Module (Join-Path $repo 'source/Dumps.psm1') -Force
    $dumpJob = Start-ProcessDump -Tool (Join-Path $repo 'tools/procdump/procdump64.exe') -TargetId $target.Id -Session $output
    if (-not $dumpJob.Process.WaitForExit(45000)) { throw 'The fixture snapshot timed out.' }
    $dump = Complete-ProcessDump -Job $dumpJob
    $dumpJob = $null
    if (-not $dump.complete) { throw 'The fixture snapshot is incomplete.' }
    $module = Join-Path $output 'module'
    & $Python (Join-Path $repo 'source/reverse/Export-DumpModule.py') $dump.path --module GhidraFixture.exe --output $module
    if ($LASTEXITCODE -ne 0) { throw 'Fixture module export failed.' }
    $manifest = Get-Content -LiteralPath (Join-Path $module 'module.json') -Raw | ConvertFrom-Json
    $rva = & $Python -c 'import pefile,sys; p=pefile.PE(sys.argv[1]); print(next(s.address for s in p.DIRECTORY_ENTRY_EXPORT.symbols if s.name==b"AllocateEntity"))' $fixture
    if ($LASTEXITCODE -ne 0) { throw 'Fixture export lookup failed.' }
    $entry = ([Convert]::ToUInt64($manifest.baseAddress.Substring(2),16) + [uint64]$rva).ToString('x')
    $identityPath = Join-Path $output 'identity.json'
    $identity = Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json
    $identity | Add-Member -NotePropertyName modules -NotePropertyValue @(@{ name='GhidraFixture.exe'; baseAddress=$manifest.baseAddress; size=$manifest.imageSize })
    $identity | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $identityPath -Encoding utf8
    $boundaries = Join-Path $output 'functions.json'
    & $Python (Join-Path $repo 'source/reverse/Export-UnwindFunctions.py') $dump.path --executable $fixture --identity $identityPath --rva $rva --output $boundaries
    if ($LASTEXITCODE -ne 0) { throw 'Fixture function boundary export failed.' }
    $strings = Join-Path $output 'strings.json'
    & $Python (Join-Path $repo 'source/reverse/Find-DumpStrings.py') (Join-Path $module 'module.json') --pattern 'fixture entity pool exhausted' --output $strings
    if ($LASTEXITCODE -ne 0) { throw 'Fixture string export failed.' }
    New-Item -ItemType Directory -Path (Join-Path $output 'projects') -Force | Out-Null
    $env:JAVA_HOME = $JavaHome
    & (Join-Path $GhidraDirectory 'support/analyzeHeadless.bat') (Join-Path $output 'projects') Fixture -import $fixture -noanalysis -scriptPath (Join-Path $repo 'source/ghidra') -postScript LoadDumpRanges.java (Join-Path $module 'module.json') -postScript DefineStrings.java $strings -postScript DefineStrings.java $strings -postScript DefineUnwindFunctions.java $boundaries -postScript EngineSurvey.java (Join-Path $output 'analysis') 'fixture entity pool exhausted' $entry -max-cpu 2 -log (Join-Path $output 'ghidra.log') > (Join-Path $output 'headless.stdout.txt') 2>&1
    if ($LASTEXITCODE -ne 0 -or (Get-Content -LiteralPath (Join-Path $output 'headless.stdout.txt') -Raw) -match 'REPORT SCRIPT ERROR') { throw 'Ghidra failed. Read headless.stdout.txt.' }
    $survey = Get-Content -LiteralPath (Join-Path $output 'analysis/survey.json') -Raw | ConvertFrom-Json
    $decompiled = Get-Content -LiteralPath (Join-Path $output "analysis/function-$entry.c") -Raw
    if ($survey.imageBase -ne $manifest.baseAddress.Substring(2) -or -not $survey.functions[0].complete -or $decompiled -notmatch '0x20' -or $decompiled -notmatch '-1') {
        throw 'The captured fixture limit check did not decompile correctly.'
    }
    if ($survey.strings.Count -ne 1 -or @($survey.strings[0].references | Where-Object function -eq $entry).Count -eq 0) { throw 'The fixture error cross-reference is missing.' }
    $badBoundaries = Get-Content -LiteralPath $boundaries -Raw | ConvertFrom-Json
    $badBoundaries.sha256 = '0' * 64
    $badBoundaryPath = Join-Path $output 'wrong-hash-functions.json'
    $badBoundaries | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $badBoundaryPath -Encoding utf8
    $repositoryOutput = Join-Path $repo "lab/evidence/ghidra-output-check/$([Guid]::NewGuid().ToString('N'))"
    $existingOutput = Join-Path $output 'existing-survey'
    New-Item -ItemType Directory -Path $existingOutput | Out-Null
    $sentinel = Join-Path $existingOutput 'survey.json'
    [IO.File]::WriteAllText($sentinel, 'existing evidence')
    $guardLog = Join-Path $output 'guards.stdout.txt'
    & (Join-Path $GhidraDirectory 'support/analyzeHeadless.bat') (Join-Path $output 'projects') Fixture -process GhidraFixture.exe -noanalysis -readOnly -scriptPath (Join-Path $repo 'source/ghidra') -postScript DefineUnwindFunctions.java $badBoundaryPath -postScript EngineSurvey.java $repositoryOutput 'fixture entity pool exhausted' -postScript EngineSurvey.java $existingOutput 'fixture entity pool exhausted' -max-cpu 2 > $guardLog 2>&1
    $guardText = Get-Content -LiteralPath $guardLog -Raw
    if ($LASTEXITCODE -ne 0 -or [regex]::Matches($guardText, 'REPORT SCRIPT ERROR').Count -ne 3 -or
        -not $guardText.Contains('different executable SHA256') -or -not $guardText.Contains('outside the repository') -or
        -not $guardText.Contains('new survey output directory') -or (Test-Path -LiteralPath $repositoryOutput) -or
        (Get-Content -LiteralPath $sentinel -Raw) -ne 'existing evidence') {
        throw 'Ghidra identity or output guards failed. Read guards.stdout.txt.'
    }
    [PSCustomObject]@{
        passed=$true
        checks=@('Captures a real native fixture.', 'Imports captured ranges at their ASLR addresses.', 'Defines captured strings on repeat runs.', 'Uses captured unwind metadata for function boundaries.', 'Traces the error string to its allocation function.', 'Decompiles the fixture pool bound and failure return.', 'Rejects boundaries from a different executable.', 'Rejects survey output inside the repository.', 'Preserves existing survey evidence.')
        output=$output
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $output 'report.json') -Encoding utf8
    Write-Output "PASS: $output"
} finally {
    if ($null -ne $dumpJob -and -not $dumpJob.Process.HasExited) { $dumpJob.Process.Kill() }
    if (-not $target.HasExited) { $target.Kill() }
}
