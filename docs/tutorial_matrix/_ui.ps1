# Win32 UI driver for LightOS — clicks/typing in PHYSICAL pixels (DPI-aware).
# Usage:
#   _ui.ps1 fg                         -> bring LightOS to foreground (by window title)
#   _ui.ps1 move  X Y
#   _ui.ps1 click X Y
#   _ui.ps1 dclick X Y
#   _ui.ps1 rclick X Y
#   _ui.ps1 drag  X1 Y1 X2 Y2
#   _ui.ps1 type  "text"               -> types text into focused control (clipboard paste)
#   _ui.ps1 key   "^s"                 -> SendKeys chord (^=Ctrl, %=Alt, +=Shift, {ENTER},{TAB},{ESC})
#   _ui.ps1 scroll X Y AMT             -> wheel at (X,Y); AMT>0 up, <0 down
#   _ui.ps1 getpos
param([Parameter(Mandatory=$true)][string]$cmd,
      [string]$a1, [string]$a2, [string]$a3, [string]$a4)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class U {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern IntPtr FindWindow(string c, string n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  public const uint LEFTDOWN=0x02, LEFTUP=0x04, RIGHTDOWN=0x08, RIGHTUP=0x10, WHEEL=0x800;
}
"@
[void][U]::SetProcessDPIAware()
Add-Type -AssemblyName System.Windows.Forms

function Find-LightOS {
  # Find top-level window whose title is exactly "LightOS"
  $h = [U]::FindWindow($null, "LightOS")
  return $h
}
function Foreground-LightOS {
  $h = Find-LightOS
  if ($h -ne [IntPtr]::Zero) {
    [void][U]::ShowWindow($h, 3)   # maximize
    [void][U]::BringWindowToTop($h)
    [void][U]::SetForegroundWindow($h)
    Start-Sleep -Milliseconds 200
  }
  return $h
}
function Do-Click([int]$x,[int]$y,[uint32]$down,[uint32]$up){
  [void][U]::SetCursorPos($x,$y); Start-Sleep -Milliseconds 60
  [U]::mouse_event($down,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 40
  [U]::mouse_event($up,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 80
}

switch ($cmd) {
  "fg"     { $h = Foreground-LightOS; "fg handle=$h" }
  "getpos" { $p=New-Object U+POINT; [void][U]::GetCursorPos([ref]$p); "pos=$($p.X),$($p.Y)" }
  "move"   { [void][U]::SetCursorPos([int]$a1,[int]$a2); "moved $a1,$a2" }
  "click"  { Do-Click ([int]$a1) ([int]$a2) ([U]::LEFTDOWN) ([U]::LEFTUP); "click $a1,$a2" }
  "dclick" { Do-Click ([int]$a1) ([int]$a2) ([U]::LEFTDOWN) ([U]::LEFTUP); Start-Sleep -Milliseconds 60; Do-Click ([int]$a1) ([int]$a2) ([U]::LEFTDOWN) ([U]::LEFTUP); "dclick $a1,$a2" }
  "rclick" { Do-Click ([int]$a1) ([int]$a2) ([U]::RIGHTDOWN) ([U]::RIGHTUP); "rclick $a1,$a2" }
  "drag"   {
    $x1=[int]$a1; $y1=[int]$a2; $x2=[int]$a3; $y2=[int]$a4
    [void][U]::SetCursorPos($x1,$y1); Start-Sleep -Milliseconds 120
    [U]::mouse_event([U]::LEFTDOWN,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 150
    $steps=18
    for($i=1;$i -le $steps;$i++){
      $xx=[int]($x1+($x2-$x1)*$i/$steps); $yy=[int]($y1+($y2-$y1)*$i/$steps)
      [void][U]::SetCursorPos($xx,$yy); Start-Sleep -Milliseconds 25
    }
    Start-Sleep -Milliseconds 150
    [U]::mouse_event([U]::LEFTUP,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 120
    "drag $x1,$y1 -> $x2,$y2"
  }
  "type"   {
    [System.Windows.Forms.Clipboard]::SetText($a1)
    Start-Sleep -Milliseconds 80
    [System.Windows.Forms.SendKeys]::SendWait("^v")
    Start-Sleep -Milliseconds 120
    "typed (paste): $a1"
  }
  "key"    { [System.Windows.Forms.SendKeys]::SendWait($a1); Start-Sleep -Milliseconds 120; "key $a1" }
  "scroll" {
    [void][U]::SetCursorPos([int]$a1,[int]$a2); Start-Sleep -Milliseconds 60
    $amt=[int]$a3
    [U]::mouse_event([U]::WHEEL,0,0,[uint32]($amt*120),[IntPtr]::Zero)
    "scroll $a1,$a2 amt=$amt"
  }
  default  { "unknown cmd $cmd" }
}
