#Requires -Version 7.0
param([Parameter(Mandatory)][string]$OutputDirectory,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
# Reuse the owned argv recorder build and production transport E2E.
& (Join-Path $PSScriptRoot 'SteamBuild.ps1') -OutputDirectory $OutputDirectory -Python $Python
if($LASTEXITCODE -ne 0){throw 'Owned production Steam transport verification failed.'}
& $Python -B (Join-Path $PSScriptRoot 'SteamControlE2E.py') --output (Join-Path $OutputDirectory 'control-e2e') --target (Join-Path $OutputDirectory 'OwnedSteamLate.exe')
if($LASTEXITCODE -ne 0){throw 'Owned stock late-control Steam transport verification failed.'}
