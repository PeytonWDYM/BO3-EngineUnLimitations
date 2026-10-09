#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Executable,[Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
$exe=(Get-Item -LiteralPath $Executable).FullName
if (Test-Path -LiteralPath $Output) { throw 'Use a new GUI evidence folder.' }
New-Item -ItemType Directory -Path $Output | Out-Null
if (!$IsWindows) {
    # Under Wine the setup refuses before it opens a window. Check that refusal instead of the window.
    . (Join-Path $PSScriptRoot 'Platform.ps1')
    $stderr=Join-Path $Output 'setup.stderr.txt'
    Invoke-Windows $exe 2> $stderr | Set-Content -LiteralPath (Join-Path $Output 'setup.stdout.txt')
    $exitCode=$LASTEXITCODE
    if ($exitCode -ne 1) { throw "The setup executable under Wine exited with $exitCode instead of refusing." }
    if ((Get-Content -LiteralPath $stderr -Raw) -notmatch 'does not support Proton or Wine') { throw 'The setup executable under Wine did not report the Proton refusal.' }
    @{passed=$true;scope='Wine refusal before the setup window opens. No window, Steam changes, or game launch.';exitCode=$exitCode;executableSha256=(Get-FileHash -LiteralPath $exe).Hash} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Output 'result.json')
    exit 0
}
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class OwnedWindow {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window, out Rect rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr window, IntPtr dc, uint flags);
}
'@
$parent=Start-Process -FilePath $exe -WindowStyle Hidden -PassThru
$child=$null
$ownedChildren=[Collections.Generic.Dictionary[int,Diagnostics.Process]]::new()
try {
    $deadline=[DateTime]::UtcNow.AddSeconds(20)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($parent.HasExited) { throw 'The setup executable exited before the GUI opened.' }
        $children=Get-CimInstance Win32_Process -Filter "ParentProcessId = $($parent.Id)" | Where-Object { $_.ExecutablePath -eq $exe }
        foreach ($candidate in $children) {
            $owned=Get-Process -Id $candidate.ProcessId
            $ownedChildren[$owned.Id]=$owned
            if ($owned.MainWindowTitle -eq 'BO3 500K' -and $owned.MainWindowHandle -ne 0) { $child=$owned; break }
        }
        if ($child) { break }
        Start-Sleep -Milliseconds 200
    }
    if (!$child) { throw 'The packaged GUI did not open within 20 seconds.' }
    $rect=[OwnedWindow+Rect]::new()
    if (![OwnedWindow]::GetWindowRect($child.MainWindowHandle,[ref]$rect)) { throw 'Cannot read the owned window bounds.' }
    $bitmap=[Drawing.Bitmap]::new($rect.Right-$rect.Left,$rect.Bottom-$rect.Top)
    $graphics=[Drawing.Graphics]::FromImage($bitmap)
    try {
        $dc=$graphics.GetHdc()
        try { if (![OwnedWindow]::PrintWindow($child.MainWindowHandle,$dc,2)) { throw 'Cannot capture the owned setup window.' } }
        finally { $graphics.ReleaseHdc($dc) }
        $bitmap.Save((Join-Path $Output 'setup.png'),[Drawing.Imaging.ImageFormat]::Png)
    } finally { $graphics.Dispose(); $bitmap.Dispose() }
    if (!$child.CloseMainWindow()) { throw 'Cannot close the owned setup window.' }
    if (!$parent.WaitForExit(10000)) { throw 'The setup process did not exit after its window closed.' }
    @{passed=$true;scope='Owned setup GUI opens, renders, and closes. No button activation, Steam changes, or game launch.';parentPid=$parent.Id;guiPid=$child.Id;executableSha256=(Get-FileHash -LiteralPath $exe).Hash;screenshot='setup.png'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Output 'result.json')
} finally {
    foreach ($owned in $ownedChildren.Values) {
        if (!$owned.HasExited -and $owned.Path -eq $exe) { Stop-Process -Id $owned.Id -Force }
    }
    if (!$parent.HasExited) { Stop-Process -Id $parent.Id -Force }
}
