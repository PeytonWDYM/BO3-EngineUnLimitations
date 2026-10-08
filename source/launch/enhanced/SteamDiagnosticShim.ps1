#Requires -Version 7.0
# Steam supplies the game executable followed by its unchanged arguments.
# No param block: switches in the game's argv must remain ordinary arguments.
$ErrorActionPreference = 'Stop'

function Assert-PrivatePath([string]$Path) {
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Diagnostic path redirects through a link.' }
            if (-not $item.PSIsContainer -and @($item.LinkTarget).Count -gt 0 -and $item.LinkTarget) { throw 'Diagnostic file has a link target.' }
        }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
}

Assert-PrivatePath $PSScriptRoot
$settingsPath = Join-Path $PSScriptRoot 'runtime.json'
Assert-PrivatePath $settingsPath
$settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
if ($settings.mode -cne '--no-debugger' -or $settings.capacity -cne 'stock' -or $settings.deadlineSeconds -ne 120) { throw 'Invalid stock diagnostic mode.' }
if ($args.Count -lt 1) { throw 'Steam did not supply a game executable.' }
$game = [IO.Path]::GetFullPath([string]$args[0])
if (-not $game.Equals($settings.game, [StringComparison]::OrdinalIgnoreCase)) { throw 'Steam supplied a different game executable.' }
Assert-PrivatePath $game
if ((Get-FileHash -LiteralPath $game -Algorithm SHA256).Hash -ine $settings.gameSha256) { throw 'Unsupported game executable.' }
foreach ($file in $settings.files.PSObject.Properties) {
    $path = Join-Path $PSScriptRoot $file.Name
    Assert-PrivatePath $path
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $file.Value) { throw 'Diagnostic payload hash mismatch.' }
}
Assert-PrivatePath $settings.logs
$log = Join-Path $settings.logs ('steam-control-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '-' + [Guid]::NewGuid().ToString('N') + '.jsonl')
if (Test-Path -LiteralPath $log) { throw 'Diagnostic output already exists.' }
$forward = [Collections.Generic.List[string]]::new()
for ($index = 1; $index -lt $args.Count; $index++) { $forward.Add([string]$args[$index]) }
# ArgumentList preserves empty strings and embedded quotes on every PS7 host.
# Environment and working directory inherit from the Steam-started shim.
$start = [Diagnostics.ProcessStartInfo]::new()
$start.FileName = Join-Path $PSScriptRoot 'BO3-Startup-Control.exe'
$start.UseShellExecute = $false
foreach ($argument in @('--no-debugger', '--observe-seconds', '120', $game, $log)) { $start.ArgumentList.Add($argument) }
foreach ($argument in $forward) { $start.ArgumentList.Add($argument) }
$child = [Diagnostics.Process]::Start($start)
try { $child.WaitForExit(); $result = $child.ExitCode } finally { $child.Dispose() }
exit $result
