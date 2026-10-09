[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$tools = Join-Path $repo 'tools'
$procdump = Join-Path $tools 'procdump'
$binary = Join-Path $procdump 'procdump64.exe'
New-Item -ItemType Directory -Path $procdump -Force | Out-Null
if (-not (Test-Path -LiteralPath $binary)) {
    Invoke-WebRequest -UseBasicParsing -Uri 'https://download.sysinternals.com/files/Procdump.zip' -OutFile (Join-Path $tools 'Procdump.zip')
    Expand-Archive -LiteralPath (Join-Path $tools 'Procdump.zip') -DestinationPath $procdump -Force
}
$signature = Get-AuthenticodeSignature -LiteralPath $binary
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
    throw 'ProcDump did not pass the Microsoft signature check.'
}
$manifest = [ordered]@{
    installedUtc = [DateTime]::UtcNow.ToString('o')
    procdump = @{ source = 'https://download.sysinternals.com/files/Procdump.zip'; sha256 = (Get-FileHash -LiteralPath $binary).Hash; version = (Get-Item -LiteralPath $binary).VersionInfo.FileVersion }
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $tools 'manifest.json') -Encoding UTF8
Write-Output "Tools ready: $tools"
