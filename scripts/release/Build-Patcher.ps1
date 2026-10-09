#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Output, [Parameter(Mandatory)][string]$NativeBuild, [string]$Python='python')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../source/launch/enhanced/PhysicalPath.ps1')
$repo=PhysicalPath (Join-Path $PSScriptRoot '../..')
$build=PhysicalPath $Output
if ((Test-Path -LiteralPath $build) -or $build.Equals($repo,[StringComparison]::OrdinalIgnoreCase) -or $build.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Use a new build folder outside the repository.' }
$manifest=Get-Content -LiteralPath (Join-Path $repo 'source/release.json') -Raw | ConvertFrom-Json
if ($manifest.schemaVersion -ne 1 -or $manifest.builds.Count -ne 1) { throw 'This builder requires one complete verified native profile.' }
$profile=$manifest.builds[0]
foreach ($entry in $profile.files.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path $NativeBuild $entry.Name)).Hash.ToLowerInvariant() -ne $entry.Value) { throw "The verified native file differs: $($entry.Name)" }
}
New-Item -ItemType Directory -Path $build | Out-Null
$native=Join-Path $build "resources/native/$($profile.id)"
New-Item -ItemType Directory -Path $native -Force | Out-Null
foreach ($entry in $profile.files.PSObject.Properties) { Copy-Item -LiteralPath (Join-Path $NativeBuild $entry.Name) -Destination $native }
Copy-Item -LiteralPath (Join-Path $repo 'source/release.json') -Destination (Join-Path $build 'resources/release.json')
& $Python -m venv (Join-Path $build 'env')
if ($LASTEXITCODE -ne 0) { throw 'Could not create the build environment.' }
$buildPython=Join-Path $build 'env/Scripts/python.exe'
& $buildPython -m pip install --disable-pip-version-check --require-hashes --only-binary=:all: -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Pinned build dependencies could not install.' }
& $buildPython -B (Join-Path $repo 'source/tests/Test-Installer.py') --output (Join-Path $build 'tests')
if ($LASTEXITCODE -ne 0) { throw 'Installer E2E failed.' }
$dist=Join-Path $build 'dist'
& $buildPython -m PyInstaller --noconfirm --clean --onefile --console --noupx --name BO3-500K-Setup --paths (Join-Path $repo 'source') --add-data "$(Join-Path $build 'resources/release.json');." --add-data "$(Join-Path $build 'resources/native');native" --distpath $dist --workpath (Join-Path $build 'work') --specpath (Join-Path $build 'spec') (Join-Path $repo 'source/patcher/app.py')
if ($LASTEXITCODE -ne 0) { throw 'Executable packaging failed.' }
$exe=Join-Path $dist 'BO3-500K-Setup.exe'
$exeVersion=& $exe --version
if ($LASTEXITCODE -ne 0 -or $exeVersion -ne $manifest.version) { throw 'The packaged executable version differs from the release manifest.' }
& $buildPython -B (Join-Path $PSScriptRoot 'Test-Executable.py') --executable $exe --output (Join-Path $build 'executable-tests')
if ($LASTEXITCODE -ne 0) { throw 'Packaged executable E2E failed.' }
& (Join-Path $PSScriptRoot 'Test-Gui.ps1') -Executable $exe -Output (Join-Path $build 'gui-tests')
if ($LASTEXITCODE -ne 0) { throw 'Packaged GUI failed.' }
& $buildPython -B (Join-Path $PSScriptRoot 'Collect-Licenses.py') (Join-Path $dist 'licenses')
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
Copy-Item -LiteralPath (Join-Path $native 'Detours-LICENSE.md') -Destination (Join-Path $dist 'licenses/Detours-LICENSE.txt')
Copy-Item -LiteralPath (Join-Path $repo 'README.md') -Destination (Join-Path $dist 'Readme.txt')
@{version=$manifest.version;exeSha256=(Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant();manifestSha256=(Get-FileHash -LiteralPath (Join-Path $repo 'source/release.json')).Hash.ToLowerInvariant();gameplayValidated=$false;protonSupported=$false;files=@(Get-ChildItem -LiteralPath $dist -Recurse -File | ForEach-Object { @{path=[IO.Path]::GetRelativePath($dist,$_.FullName).Replace('\','/');sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()} })} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $dist 'build.json') -Encoding utf8
Compress-Archive -LiteralPath (Get-ChildItem -LiteralPath $dist | ForEach-Object FullName) -DestinationPath (Join-Path $build "BO3-500K-$($manifest.version)-windows.zip")
