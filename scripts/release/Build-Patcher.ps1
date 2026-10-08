[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Output,
    [string]$Python = 'python',
    [string]$UpxArchive,
    [string]$UpxSourceArchive,
    [string]$EnhancedBuild
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$buildRoot = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $buildRoot) { throw 'Select a new build output folder.' }
$manifest = Join-Path $repo 'source/patchplans/release.json'
if (-not (Test-Path -LiteralPath $manifest)) { throw 'The completed release manifest is missing.' }
$plan = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
if ($plan.schemaVersion -ne 1 -or $plan.status -ne 'ready' -or $plan.features.Count -eq 0) {
    throw 'The release manifest is incomplete.'
}
New-Item -ItemType Directory -Path $buildRoot | Out-Null
$venv = Join-Path $buildRoot 'build-env'
& $Python -m venv $venv
if ($LASTEXITCODE -ne 0) { throw 'Python could not create the build environment.' }
$buildPython = Join-Path $venv 'Scripts/python.exe'
& $buildPython -m pip install --disable-pip-version-check --require-hashes --only-binary=:all: -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'The pinned build dependencies could not install.' }
& $PSScriptRoot/Test-Patcher.ps1 -Output (Join-Path $buildRoot 'tests') -Python $buildPython
$upxHash = 'eabc6792a347d45e945be7748423e7868fd01b0d2bcaa2f4b1031fd71ff69bda'
$exeHash = 'd20ebe0b7b22b6be968c8c34be61f94ddea12cb11462e2cec27f548ef9574df8'
$archive = Join-Path $buildRoot 'upx-5.2.1-win64.zip'
if ($UpxArchive) {
    Copy-Item -LiteralPath $UpxArchive -Destination $archive
} else {
    Invoke-WebRequest -Uri 'https://github.com/upx/upx/releases/download/v5.2.1/upx-5.2.1-win64.zip' -OutFile $archive
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $upxHash) {
    throw 'The official UPX archive has an unexpected hash.'
}
$tools = Join-Path $buildRoot 'resources/upx'
New-Item -ItemType Directory -Path $tools -Force | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $buildRoot 'upx-extracted')
$upx = Join-Path $buildRoot 'upx-extracted/upx-5.2.1-win64/upx.exe'
if ((Get-FileHash -LiteralPath $upx -Algorithm SHA256).Hash.ToLowerInvariant() -ne $exeHash) {
    throw 'The official UPX executable has an unexpected hash.'
}
Copy-Item -LiteralPath $upx -Destination (Join-Path $tools 'upx.exe')
Copy-Item -LiteralPath (Join-Path $buildRoot 'upx-extracted/upx-5.2.1-win64/COPYING') -Destination (Join-Path $tools 'COPYING')
Copy-Item -LiteralPath (Join-Path $buildRoot 'upx-extracted/upx-5.2.1-win64/LICENSE') -Destination (Join-Path $tools 'LICENSE')
$sourceNotice = @'
UPX 5.2.1 is a separate bundled tool.
Its license and copying terms are in this folder.
Corresponding source: https://github.com/upx/upx/releases/download/v5.2.1/upx-5.2.1-src.tar.xz
Release: https://github.com/upx/upx/releases/tag/v5.2.1
The patcher invokes UPX only to unpack the user's verified native module.
'@
Set-Content -LiteralPath (Join-Path $tools 'SOURCE.txt') -Value $sourceNotice -Encoding utf8
$data = Join-Path $buildRoot 'resources/patchplans'
New-Item -ItemType Directory -Path $data | Out-Null
Get-ChildItem -LiteralPath (Join-Path $repo 'source/patchplans') -Filter '*.json' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $data
}
$dist = Join-Path $buildRoot 'dist'
$arguments = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console', '--noupx', '--name', 'BO3-Engine-UnLimitations', '--paths', (Join-Path $repo 'source'), '--add-data', "$data;patchplans", '--add-data', "$tools;upx", '--distpath', $dist, '--workpath', (Join-Path $buildRoot 'work'), '--specpath', (Join-Path $buildRoot 'spec'))
$enhancedManifest = Join-Path $repo 'source/patcher/enhanced_manifest.json'
if ($EnhancedBuild) {
    $enhanced = Get-Content -LiteralPath $enhancedManifest -Raw | ConvertFrom-Json
    if ($enhanced.version -ne $plan.version) { throw 'Enhanced payload version differs from the patcher release.' }
    $enhancedResources = Join-Path $buildRoot 'resources/enhanced'
    New-Item -ItemType Directory -Path $enhancedResources | Out-Null
    foreach ($entry in $enhanced.files.PSObject.Properties) {
        $inputFile = Join-Path $EnhancedBuild $entry.Name
        if ((Get-FileHash -LiteralPath $inputFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
            throw "The reviewed enhanced launcher payload differs: $($entry.Name)"
        }
        Copy-Item -LiteralPath $inputFile -Destination (Join-Path $enhancedResources $entry.Name)
    }
    Copy-Item -LiteralPath $enhancedManifest -Destination (Join-Path $enhancedResources 'manifest.json')
    $arguments += @('--add-data', "$enhancedResources;enhanced")
}
foreach ($module in ($plan.features.transform | ForEach-Object { ($_ -split ':')[0] } | Sort-Object -Unique)) {
    $arguments += @('--hidden-import', $module)
}
$arguments += (Join-Path $repo 'source/patcher/app.py')
& $buildPython @arguments
if ($LASTEXITCODE -ne 0) { throw 'The Windows executable build failed.' }
$licenses = Join-Path $dist 'UPX-licenses'
New-Item -ItemType Directory -Path $licenses | Out-Null
foreach ($name in @('COPYING', 'LICENSE', 'SOURCE.txt')) {
    Copy-Item -LiteralPath (Join-Path $tools $name) -Destination $licenses
}
$sourceArchive = Join-Path $dist 'upx-5.2.1-src.tar.xz'
if ($UpxSourceArchive) {
    Copy-Item -LiteralPath $UpxSourceArchive -Destination $sourceArchive
} else {
    Invoke-WebRequest -Uri 'https://github.com/upx/upx/releases/download/v5.2.1/upx-5.2.1-src.tar.xz' -OutFile $sourceArchive
}
$sourceHash = 'a7d457be4ef942e46844ee8f301206b111394cbcbde3599747a6904c54ff116b'
if ((Get-FileHash -LiteralPath $sourceArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceHash) {
    throw 'The official UPX source archive has an unexpected hash.'
}
Copy-Item -LiteralPath (Join-Path $repo 'docs/patcher.md') -Destination (Join-Path $dist 'README-patcher.md')
if (Test-Path -LiteralPath (Join-Path $repo 'LICENSE')) {
    Copy-Item -LiteralPath (Join-Path $repo 'LICENSE') -Destination (Join-Path $dist 'LICENSE-patcher')
}
$artifact = Join-Path $dist 'BO3-Engine-UnLimitations.exe'
if ($EnhancedBuild) {
    Copy-Item -LiteralPath (Join-Path $enhancedResources 'Detours-LICENSE.md') -Destination (Join-Path $dist 'Detours-LICENSE.md')
    Copy-Item -LiteralPath $enhancedManifest -Destination (Join-Path $dist 'enhanced-launcher-manifest.json')
}
& $buildPython (Join-Path $PSScriptRoot 'Collect-Licenses.py') (Join-Path $dist 'third-party-licenses')
if ($LASTEXITCODE -ne 0) { throw 'The dependency license collection failed.' }
& $buildPython (Join-Path $repo 'source/tests/patcher/test_executable.py') --executable $artifact --manifest $manifest --output (Join-Path $buildRoot 'executable-tests')
if ($LASTEXITCODE -ne 0) { throw 'The packaged executable checks failed.' }
$enhancedChecks = @((Join-Path $repo 'source/tests/patcher/test_packaged_enhanced.py'), '--executable', $artifact, '--manifest', $enhancedManifest, '--output', (Join-Path $buildRoot 'enhanced-executable-tests'))
if ($EnhancedBuild) { $enhancedChecks += '--bundled' }
& $buildPython @enhancedChecks
if ($LASTEXITCODE -ne 0) { throw 'The optional enhanced payload checks failed.' }
& $buildPython (Join-Path $repo 'source/tests/patcher/test_packaged_steam.py') --executable $artifact --manifest $manifest --output (Join-Path $buildRoot 'steam-executable-tests')
if ($LASTEXITCODE -ne 0) { throw 'The frozen Steam setup checks failed.' }
$report = [ordered]@{
    schema = 1
    version = $plan.version
    artifact = 'BO3-Engine-UnLimitations.exe'
    artifactSha256 = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    artifactBytes = (Get-Item -LiteralPath $artifact).Length
    manifestSha256 = (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant()
    upxArchiveSha256 = $upxHash
    upxExecutableSha256 = $exeHash
    upxSourceSha256 = $sourceHash
    timestampUtc = [DateTime]::UtcNow.ToString('o')
    containsGameAssets = $false
    gameplayValidated = $false
    friendsValidated = $false
    enhancedLauncherBundled = [bool]$EnhancedBuild
    enhancedLauncherStatus = $(if ($EnhancedBuild) { 'experimental-unvalidated-game' } else { 'not-bundled' })
}
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dist 'build.json') -Encoding utf8
Write-Output "Release files: $dist"
