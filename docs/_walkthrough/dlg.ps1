# Helper: find/operate the (modal) dialog or popup window that LightOS opened.
# A dialog = a VISIBLE top-level window owned by the SAME python process as the
# main "LightOS" window, whose title is NOT "LightOS"/"LightOS ...".
#
# Usage:
#   dlg.ps1 find              -> "hwnd|title|L|T|R|B  WxH"  (or "none")
#   dlg.ps1 fg                -> bring the dialog to the foreground (topmost)
#   dlg.ps1 key  "{ESC}"      -> foreground dialog, then SendKeys chord
#   dlg.ps1 click X Y         -> foreground dialog, then click physical X,Y
param([Parameter(Mandatory=$true)][string]$cmd,[string]$a1,[string]$a2,[string]$a3)

Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices;
public class DL {
  public delegate bool EP(IntPtr h, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool EnumWindows(EP cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte sc, uint f, IntPtr e);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint dx,uint dy,uint d,IntPtr e);

  public static uint MainPid=0;
  // find the python pid that owns the main "LightOS" window
  public static void FindMainPid() {
    MainPid=0;
    EnumWindows((h,l)=>{ if(IsWindowVisible(h)){ var sb=new StringBuilder(300); GetWindowText(h,sb,300);
      var t=sb.ToString();
      if(t.Equals("LightOS",StringComparison.OrdinalIgnoreCase) || t.StartsWith("LightOS ",StringComparison.OrdinalIgnoreCase)){
        uint pid; GetWindowThreadProcessId(h,out pid);
        try { var p=System.Diagnostics.Process.GetProcessById((int)pid);
          if(p.ProcessName.ToLower().Contains("python")){ MainPid=pid; return false; } } catch {}
      } } return true; }, IntPtr.Zero);
  }
  public static IntPtr DlgHwnd=IntPtr.Zero; public static string DlgTitle="";
  public static IntPtr Find() {
    FindMainPid(); DlgHwnd=IntPtr.Zero; DlgTitle="";
    if(MainPid==0) return IntPtr.Zero;
    EnumWindows((h,l)=>{ if(IsWindowVisible(h)){
      uint pid; GetWindowThreadProcessId(h,out pid);
      if(pid==MainPid){
        var sb=new StringBuilder(400); GetWindowText(h,sb,400); var t=sb.ToString();
        if(!(t.Equals("LightOS",StringComparison.OrdinalIgnoreCase) || t.StartsWith("LightOS ",StringComparison.OrdinalIgnoreCase))){
          RECT r; GetWindowRect(h,out r);
          if((r.R-r.L)>40 && (r.B-r.T)>30){ DlgHwnd=h; DlgTitle=t; return false; }
        }
      } } return true; }, IntPtr.Zero);
    return DlgHwnd;
  }
  public static IntPtr Force() {
    IntPtr h=Find(); if(h==IntPtr.Zero) return IntPtr.Zero;
    keybd_event(0x12,0,0,IntPtr.Zero); keybd_event(0x12,0,2,IntPtr.Zero);
    IntPtr fg=GetForegroundWindow(); uint cur=GetCurrentThreadId(); uint p1,p2;
    uint fgt=GetWindowThreadProcessId(fg,out p1); uint tgt=GetWindowThreadProcessId(h,out p2);
    AttachThreadInput(cur,fgt,true); AttachThreadInput(cur,tgt,true);
    BringWindowToTop(h); SetForegroundWindow(h);
    AttachThreadInput(cur,fgt,false); AttachThreadInput(cur,tgt,false);
    return h;
  }
  public const uint LDOWN=0x02,LUP=0x04;
}
"@
[void][DL]::SetProcessDPIAware()
Add-Type -AssemblyName System.Windows.Forms

switch ($cmd) {
  "find" {
    $h=[DL]::Find()
    if($h -eq [IntPtr]::Zero){ "none" } else {
      $r=New-Object DL+RECT; [void][DL]::GetWindowRect($h,[ref]$r)
      "$h|$([DL]::DlgTitle)|$($r.L)|$($r.T)|$($r.R)|$($r.B)  $($r.R-$r.L)x$($r.B-$r.T)"
    }
  }
  "fg" { $h=[DL]::Force(); Start-Sleep -Milliseconds 200; if($h -eq [IntPtr]::Zero){"none"}else{"fg $h '$([DL]::DlgTitle)'"} }
  "key" { [void][DL]::Force(); Start-Sleep -Milliseconds 160; [System.Windows.Forms.SendKeys]::SendWait($a1); Start-Sleep -Milliseconds 120; "key $a1" }
  "click" {
    [void][DL]::Force(); Start-Sleep -Milliseconds 160
    [void][DL]::SetCursorPos([int]$a1,[int]$a2); Start-Sleep -Milliseconds 70
    [DL]::mouse_event([DL]::LDOWN,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 45
    [DL]::mouse_event([DL]::LUP,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 90
    "click $a1,$a2"
  }
  default { "unknown $cmd" }
}
