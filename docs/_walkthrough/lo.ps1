# HINWEIS: Start/Stop/Wait/Shot sind jetzt in tools/app.ps1 konsolidiert (QA-22). Dieses Skill-Toolset
# bleibt fuer die Feinsteuerung (move/click/drag/type/key/scroll/crop) erhalten.
# LightOS walkthrough driver — robust foreground + input + screenshot (DPI-aware, physical px).
# The target is the VISIBLE window whose title is "LightOS" / "LightOS ..." AND owned by a python process
# (this excludes the "lightos-main - Datei-Explorer" window and the console).
#
# Usage:
#   lo.ps1 fg                         -> force LightOS foreground+topmost; prints hwnd + window rect
#   lo.ps1 rect                       -> print LightOS window rect (L T R B  WxH)
#   lo.ps1 untop                      -> drop topmost (call at end of a session)
#   lo.ps1 move   X Y
#   lo.ps1 click  X Y
#   lo.ps1 dclick X Y
#   lo.ps1 rclick X Y
#   lo.ps1 drag   X1 Y1 X2 Y2
#   lo.ps1 type   "text"              -> paste text into focused control
#   lo.ps1 key    "^s"                -> SendKeys chord (^Ctrl %Alt +Shift {ENTER}{TAB}{ESC})
#   lo.ps1 scroll X Y AMT             -> wheel at (X,Y); AMT>0 up
#   lo.ps1 shot   Path [TargetW]      -> full virtual-screen PNG; TargetW>0 scales width (0=full res)
#   lo.ps1 crop   Path X Y W H [TargetW]
param([Parameter(Mandatory=$true)][string]$cmd,
      [string]$a1,[string]$a2,[string]$a3,[string]$a4,[string]$a5,[string]$a6)

Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices;
public class LO {
  public delegate bool EP(IntPtr h, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool EnumWindows(EP cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x,int y,int cx,int cy, uint flags);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte sc, uint f, IntPtr e);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint dx,uint dy,uint d,IntPtr e);
  public const uint LDOWN=0x02,LUP=0x04,RDOWN=0x08,RUP=0x10,WHEEL=0x800;

  public static IntPtr Hwnd=IntPtr.Zero; public static string Title="";
  public static IntPtr Find() {
    Hwnd=IntPtr.Zero; Title="";
    EnumWindows((h,l)=>{ if(IsWindowVisible(h)){ var sb=new StringBuilder(300); GetWindowText(h,sb,300);
      var t=sb.ToString();
      if(t.Equals("LightOS",StringComparison.OrdinalIgnoreCase) || t.StartsWith("LightOS ",StringComparison.OrdinalIgnoreCase)){
        uint pid; GetWindowThreadProcessId(h,out pid);
        try { var p=System.Diagnostics.Process.GetProcessById((int)pid);
          if(p.ProcessName.ToLower().Contains("python")){ Hwnd=h; Title=t; return false; } } catch {}
      } } return true; }, IntPtr.Zero);
    return Hwnd;
  }
  public static IntPtr Force(bool maximize) {
    IntPtr h=Find(); if(h==IntPtr.Zero) return IntPtr.Zero;
    keybd_event(0x12,0,0,IntPtr.Zero); keybd_event(0x12,0,2,IntPtr.Zero);
    IntPtr fg=GetForegroundWindow(); uint cur=GetCurrentThreadId(); uint p1,p2;
    uint fgt=GetWindowThreadProcessId(fg,out p1); uint tgt=GetWindowThreadProcessId(h,out p2);
    AttachThreadInput(cur,fgt,true); AttachThreadInput(cur,tgt,true);
    if(maximize) ShowWindow(h,3); else ShowWindow(h,9);
    BringWindowToTop(h); SetForegroundWindow(h);
    SetWindowPos(h,new IntPtr(-1),0,0,0,0,0x0003); SetWindowPos(h,new IntPtr(-1),0,0,0,0,0x0003);
    AttachThreadInput(cur,fgt,false); AttachThreadInput(cur,tgt,false);
    return h;
  }
  public static void Untop(){ IntPtr h=Find(); if(h!=IntPtr.Zero) SetWindowPos(h,new IntPtr(-2),0,0,0,0,0x0003); }
  // Foreground assert before each input action (Alt-tap defeats the foreground lock; TOPMOST keeps it on top).
  // No maximize (avoids flicker). Mirrors the proven Force() path minus ShowWindow.
  public static IntPtr Ensure() {
    IntPtr h=Find(); if(h==IntPtr.Zero) return IntPtr.Zero;
    IntPtr fg=GetForegroundWindow(); if(fg==h) return h;
    // Wenn das Vordergrundfenster zum SELBEN Prozess gehoert (eigenes Menue/Popup/
    // nicht-modaler Dialog von LightOS), NICHT das Hauptfenster nach vorn zwingen —
    // das wuerde das Menue/Popup schliessen, bevor der Klick ankommt.
    uint efp,ehp; GetWindowThreadProcessId(fg,out efp); GetWindowThreadProcessId(h,out ehp);
    if(efp==ehp) return h;
    keybd_event(0x12,0,0,IntPtr.Zero); keybd_event(0x12,0,2,IntPtr.Zero);
    uint cur=GetCurrentThreadId(); uint p1,p2;
    uint fgt=GetWindowThreadProcessId(fg,out p1); uint tgt=GetWindowThreadProcessId(h,out p2);
    AttachThreadInput(cur,fgt,true); AttachThreadInput(cur,tgt,true);
    BringWindowToTop(h); SetForegroundWindow(h);
    SetWindowPos(h,new IntPtr(-1),0,0,0,0,0x0003);
    AttachThreadInput(cur,fgt,false); AttachThreadInput(cur,tgt,false);
    return h;
  }
}
"@
[void][LO]::SetProcessDPIAware()
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Click([int]$x,[int]$y,[uint32]$d,[uint32]$u){
  [void][LO]::Ensure(); Start-Sleep -Milliseconds 140
  [void][LO]::SetCursorPos($x,$y); Start-Sleep -Milliseconds 70
  [LO]::mouse_event($d,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 45
  [LO]::mouse_event($u,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 90
}
function SaveShot([int]$X,[int]$Y,[int]$W,[int]$H,[string]$Path,[int]$TargetW){
  $bmp = New-Object System.Drawing.Bitmap($W,$H)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($X,$Y,0,0,(New-Object System.Drawing.Size($W,$H)))
  if($TargetW -gt 0 -and $TargetW -lt $W){
    $th=[int]($H * $TargetW / $W)
    $sb = New-Object System.Drawing.Bitmap($TargetW,$th)
    $sg = [System.Drawing.Graphics]::FromImage($sb)
    $sg.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $sg.DrawImage($bmp,0,0,$TargetW,$th)
    $sb.Save($Path,[System.Drawing.Imaging.ImageFormat]::Png); $sg.Dispose(); $sb.Dispose()
    "saved $Path (${TargetW}x${th}, from ${W}x${H})"
  } else {
    $bmp.Save($Path,[System.Drawing.Imaging.ImageFormat]::Png)
    "saved $Path (${W}x${H})"
  }
  $g.Dispose(); $bmp.Dispose()
}

switch ($cmd) {
  "fg"     { $h=[LO]::Force($true); $r=New-Object LO+RECT; [void][LO]::GetWindowRect($h,[ref]$r); Start-Sleep -Milliseconds 250; "fg hwnd=$h title='$([LO]::Title)' rect=$($r.L),$($r.T),$($r.R),$($r.B) $($r.R-$r.L)x$($r.B-$r.T) foreground=$([LO]::GetForegroundWindow())" }
  "rect"   { $h=[LO]::Find(); $r=New-Object LO+RECT; [void][LO]::GetWindowRect($h,[ref]$r); "hwnd=$h rect=$($r.L),$($r.T),$($r.R),$($r.B) $($r.R-$r.L)x$($r.B-$r.T)" }
  "untop"  { [LO]::Untop(); "untopped" }
  "move"   { [void][LO]::SetCursorPos([int]$a1,[int]$a2); "moved $a1,$a2" }
  "click"  { Click ([int]$a1) ([int]$a2) ([LO]::LDOWN) ([LO]::LUP); "click $a1,$a2" }
  "dclick" { Click ([int]$a1) ([int]$a2) ([LO]::LDOWN) ([LO]::LUP); Start-Sleep -Milliseconds 70; Click ([int]$a1) ([int]$a2) ([LO]::LDOWN) ([LO]::LUP); "dclick $a1,$a2" }
  "rclick" { Click ([int]$a1) ([int]$a2) ([LO]::RDOWN) ([LO]::RUP); "rclick $a1,$a2" }
  "drag"   {
    [void][LO]::Ensure(); Start-Sleep -Milliseconds 140
    $x1=[int]$a1;$y1=[int]$a2;$x2=[int]$a3;$y2=[int]$a4
    [void][LO]::SetCursorPos($x1,$y1); Start-Sleep -Milliseconds 140
    [LO]::mouse_event([LO]::LDOWN,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 170
    $steps=20; for($i=1;$i -le $steps;$i++){ $xx=[int]($x1+($x2-$x1)*$i/$steps); $yy=[int]($y1+($y2-$y1)*$i/$steps); [void][LO]::SetCursorPos($xx,$yy); Start-Sleep -Milliseconds 28 }
    Start-Sleep -Milliseconds 160; [LO]::mouse_event([LO]::LUP,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 140
    "drag $x1,$y1 -> $x2,$y2"
  }
  "type"   { [void][LO]::Ensure(); Start-Sleep -Milliseconds 140; [System.Windows.Forms.Clipboard]::SetText($a1); Start-Sleep -Milliseconds 90; [System.Windows.Forms.SendKeys]::SendWait("^v"); Start-Sleep -Milliseconds 130; "typed: $a1" }
  "key"    { [void][LO]::Ensure(); Start-Sleep -Milliseconds 140; [System.Windows.Forms.SendKeys]::SendWait($a1); Start-Sleep -Milliseconds 140; "key $a1" }
  "scroll" { [void][LO]::Ensure(); Start-Sleep -Milliseconds 140; [void][LO]::SetCursorPos([int]$a1,[int]$a2); Start-Sleep -Milliseconds 60; [LO]::mouse_event([LO]::WHEEL,0,0,[uint32]([int64]([int]$a3*120) -band 0xFFFFFFFFL),[IntPtr]::Zero); "scroll $a1,$a2 amt=$a3" }
  "shot"   { $b=[System.Windows.Forms.SystemInformation]::VirtualScreen; $tw=0; if($a2){$tw=[int]$a2}; SaveShot $b.X $b.Y $b.Width $b.Height $a1 $tw }
  "crop"   { $tw=0; if($a6){$tw=[int]$a6}; SaveShot ([int]$a2) ([int]$a3) ([int]$a4) ([int]$a5) $a1 $tw }
  default  { "unknown cmd $cmd" }
}
