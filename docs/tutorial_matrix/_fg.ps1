# HINWEIS: durch tools/app.ps1 'fg' ersetzt/konsolidiert (QA-22).
# Robustly force the LightOS window to the foreground+topmost (defeats foreground lock).
# Finds the window by title SUBSTRING "LightOS" (title changes when a show loads).
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class FG {
  public delegate bool EP(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool EnumWindows(EP cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte sc, uint f, IntPtr e);
  static IntPtr _found = IntPtr.Zero;
  public static IntPtr FindByTitle(string sub) {
    _found = IntPtr.Zero;
    // Match the GUI window whose title STARTS WITH "LightOS" (the console window's
    // title is the working-directory path and starts with "C:").
    EnumWindows((h,l)=>{ if(IsWindowVisible(h)){ var sb=new StringBuilder(300); GetWindowText(h,sb,300);
      var t=sb.ToString(); if(t.StartsWith(sub, StringComparison.OrdinalIgnoreCase)){ _found=h; return false; } } return true; }, IntPtr.Zero);
    return _found;
  }
  public static IntPtr Force(string sub, bool maximize) {
    IntPtr h = FindByTitle(sub);
    if (h == IntPtr.Zero) return IntPtr.Zero;
    keybd_event(0x12, 0, 0, IntPtr.Zero);
    keybd_event(0x12, 0, 2, IntPtr.Zero);
    IntPtr fg = GetForegroundWindow();
    uint curThread = GetCurrentThreadId();
    uint p1, p2;
    uint fgThread = GetWindowThreadProcessId(fg, out p1);
    uint tgtThread = GetWindowThreadProcessId(h, out p2);
    AttachThreadInput(curThread, fgThread, true);
    AttachThreadInput(curThread, tgtThread, true);
    if (maximize) ShowWindow(h, 3); else ShowWindow(h, 9);
    BringWindowToTop(h);
    SetForegroundWindow(h);
    SetWindowPos(h, new IntPtr(-1), 0,0,0,0, 0x0003);
    SetWindowPos(h, new IntPtr(-1), 0,0,0,0, 0x0003);
    AttachThreadInput(curThread, fgThread, false);
    AttachThreadInput(curThread, tgtThread, false);
    return h;
  }
}
"@
[void][FG]::SetProcessDPIAware()
$h = [FG]::Force("LightOS", $true)
Start-Sleep -Milliseconds 300
"forced fg, handle=$h, foreground-now=$([FG]::GetForegroundWindow())"
