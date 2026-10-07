param(
    [Parameter(Mandatory)][string]$Latest,
    [string]$ProofDirectory,
    [int]$ExitAfterSeconds = 0
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type -Path (Join-Path $PSScriptRoot 'OverlayWindow.cs') -ReferencedAssemblies System.Windows.Forms, System.Drawing
. (Join-Path $PSScriptRoot 'Overlay-Model.ps1')
if ($ProofDirectory) {
    $repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
    $proof = [IO.Path]::GetFullPath($ProofDirectory)
    if ($proof.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or $proof.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Keep overlay evidence outside the repository.'
    }
    $ancestor = [IO.DirectoryInfo]::new($proof)
    while ($null -ne $ancestor) {
        if ($ancestor.Exists -and ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Use an evidence path without directory junctions or symbolic links.'
        }
        $ancestor = $ancestor.Parent
    }
    if (Test-Path -LiteralPath $proof) { throw 'Use a new proof directory.' }
    New-Item -ItemType Directory -Path $proof | Out-Null
}
$form = [DiagnosticsOverlayWindow]::new()
$form.Text = 'BO3 read-only diagnostics'
$form.FormBorderStyle = 'None'
$form.TopMost = $true
$form.ShowInTaskbar = $false
$form.BackColor = [Drawing.Color]::FromArgb(18, 22, 27)
$form.Opacity = 0.88
$form.ClientSize = [Drawing.Size]::new(540, 295)
$form.StartPosition = 'Manual'
$area = [Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$form.Location = [Drawing.Point]::new($area.Right - $form.Width - 16, $area.Top + 16)
$label = [Windows.Forms.Label]::new()
$label.Location = [Drawing.Point]::new(12, 10)
$label.Size = [Drawing.Size]::new(516, 275)
$label.Font = [Drawing.Font]::new('Consolas', 11)
$label.ForeColor = [Drawing.Color]::Gainsboro
$form.Controls.Add($label)
$tray = [Windows.Forms.NotifyIcon]::new()
$tray.Icon = [Drawing.SystemIcons]::Information
$tray.Text = 'BO3 diagnostics'
$tray.Visible = $true
$menu = [Windows.Forms.ContextMenuStrip]::new()
$toggle = $menu.Items.Add('Hide/show overlay')
$toggle.Add_Click({ if ($form.Visible) { $form.Hide() } else { $form.Show() } })
$exit = $menu.Items.Add('Exit overlay')
$exit.Add_Click({ $form.Close() })
$tray.ContextMenuStrip = $menu
$started = [datetimeoffset]::UtcNow
$timer = [Windows.Forms.Timer]::new()
$timer.Interval = 1000
$timer.Add_Tick({
    try {
        # Allow the monitor to replace the file while the window reads it.
        $inputStream = [IO.File]::Open($Latest, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]'ReadWrite, Delete')
        $reader = [IO.StreamReader]::new($inputStream)
        try { $state = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        $model = Get-OverlayModel -State $state
        $label.Text = $model.Text
        $label.ForeColor = if ($model.Exhausted -or $model.Status -in @('STALE', 'STOPPED', 'READ REJECTED')) { [Drawing.Color]::Orange } else { [Drawing.Color]::Gainsboro }
        if ($ProofDirectory -and !(Test-Path -LiteralPath (Join-Path $proof 'render.json'))) {
            $bitmap = [Drawing.Bitmap]::new($form.Width, $form.Height)
            try {
                $form.DrawToBitmap($bitmap, [Drawing.Rectangle]::new(0, 0, $form.Width, $form.Height))
                $bitmap.Save((Join-Path $proof 'overlay.png'), [Drawing.Imaging.ImageFormat]::Png)
            } finally { $bitmap.Dispose() }
            @{ Text = $model.Text; Status = $model.Status; ExtendedStyles = $form.GetType().GetProperty('CreateParams', [Reflection.BindingFlags]'Instance, NonPublic').GetValue($form).ExStyle; SourceState = $state } | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $proof 'render.json')
        }
    } catch { $label.Text = "BO3 diagnostics | READ ERROR`r`n$($_.Exception.Message)"; $label.ForeColor = [Drawing.Color]::Orange }
    if ($ExitAfterSeconds -gt 0 -and ([datetimeoffset]::UtcNow - $started).TotalSeconds -ge $ExitAfterSeconds) { $form.Close() }
})
try {
    $timer.Start()
    [Windows.Forms.Application]::Run($form)
} finally {
    $timer.Dispose()
    $tray.Dispose()
    $menu.Dispose()
    $form.Dispose()
}
