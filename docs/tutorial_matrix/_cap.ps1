# Single screenshot to a file. Optional crop rect: -X -Y -W -H (physical pixels).
param(
  [Parameter(Mandatory=$true)][string]$Path,
  [int]$X = 0, [int]$Y = 0, [int]$W = 0, [int]$H = 0
)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
# Make process DPI aware so captured pixels match on-screen physical pixels.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class DpiAware {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[void][DpiAware]::SetProcessDPIAware()
if ($W -le 0 -or $H -le 0) {
  $b = [System.Windows.Forms.SystemInformation]::VirtualScreen
  $X = $b.X; $Y = $b.Y; $W = $b.Width; $H = $b.Height
}
$bmp = New-Object System.Drawing.Bitmap($W, $H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($X, $Y, 0, 0, (New-Object System.Drawing.Size($W, $H)))
$bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "saved $Path ($W x $H)"
