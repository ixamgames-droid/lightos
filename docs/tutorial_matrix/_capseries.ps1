# Capture a series of frames at an interval (for GIFs of running effects).
# Saves <OutDir>\<Prefix>_000.png ... Optional crop rect -X -Y -W -H.
param(
  [Parameter(Mandatory=$true)][string]$OutDir,
  [Parameter(Mandatory=$true)][string]$Prefix,
  [int]$Count = 12,
  [double]$IntervalMs = 400,
  [int]$X = 0, [int]$Y = 0, [int]$W = 0, [int]$H = 0
)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class DpiAware2 { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }
"@
[void][DpiAware2]::SetProcessDPIAware()
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force $OutDir | Out-Null }
if ($W -le 0 -or $H -le 0) {
  $b = [System.Windows.Forms.SystemInformation]::VirtualScreen
  $X = $b.X; $Y = $b.Y; $W = $b.Width; $H = $b.Height
}
$sz = New-Object System.Drawing.Size($W, $H)
for ($i = 0; $i -lt $Count; $i++) {
  $bmp = New-Object System.Drawing.Bitmap($W, $H)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($X, $Y, 0, 0, $sz)
  $name = "{0}\{1}_{2:000}.png" -f $OutDir, $Prefix, $i
  $bmp.Save($name, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  Start-Sleep -Milliseconds $IntervalMs
}
Write-Output "captured $Count frames -> $OutDir\$Prefix_*.png"
