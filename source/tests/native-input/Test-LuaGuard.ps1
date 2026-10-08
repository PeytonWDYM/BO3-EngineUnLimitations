param(
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$Original,
    [Parameter(Mandatory)][string]$Candidate,
    [Parameter(Mandatory)][string]$Profile,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$proof = [IO.Path]::GetFullPath($Output)
if ($proof -eq $repo -or $proof.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep native input evidence outside the repository.'
}
$ancestor = [IO.DirectoryInfo]::new($proof)
while ($null -ne $ancestor) {
    if ($ancestor.Exists -and ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Use an evidence directory without junctions or symbolic links.'
    }
    $ancestor = $ancestor.Parent
}
if (Test-Path -LiteralPath $proof) { throw 'Use a new evidence directory.' }
New-Item -ItemType Directory -Path $proof | Out-Null
& $Python (Join-Path $PSScriptRoot 'Replay-LuaGuard.py') --original $Original --candidate $Candidate --profile $Profile --output (Join-Path $proof 'replay')
if ($LASTEXITCODE -ne 0) { throw 'Native instruction replay failed.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$compiler = (Get-ChildItem -LiteralPath (Join-Path $visualStudio 'VC\Tools\MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$sdk = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10'
$sdkVersion = (Get-ChildItem -LiteralPath (Join-Path $sdk 'Lib') -Directory | Sort-Object Name -Descending | Select-Object -First 1).Name
$env:INCLUDE = "$compiler\include;$sdk\Include\$sdkVersion\um;$sdk\Include\$sdkVersion\shared;$sdk\Include\$sdkVersion\ucrt"
$env:LIB = "$compiler\lib\x64;$sdk\Lib\$sdkVersion\um\x64;$sdk\Lib\$sdkVersion\ucrt\x64"
$verifier = Join-Path $proof 'Verify-GuardImage.exe'
& (Join-Path $compiler 'bin\Hostx64\x64\cl.exe') /nologo /std:c++20 /EHsc /W4 /MD (Join-Path $PSScriptRoot 'Verify-GuardImage.cpp') "/Fe:$verifier" "/Fo:$proof\Verify-GuardImage.obj" /link /INCREMENTAL:NO
if ($LASTEXITCODE -ne 0) { throw 'Windows image verifier build failed.' }
& $verifier $Candidate | Tee-Object -FilePath (Join-Path $proof 'windows-image.json')
if ($LASTEXITCODE -ne 0) { throw 'Windows image or unwind verification failed.' }
@{ Passed = $true; CandidateSha256 = (Get-FileHash -LiteralPath $Candidate).Hash; OriginalSha256 = (Get-FileHash -LiteralPath $Original).Hash; GameExecuted = $false } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $proof 'result.json')
