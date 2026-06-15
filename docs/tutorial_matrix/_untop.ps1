# Clear the always-on-top flag on the LightOS window (run at the very end).
# Finds the window by title prefix "LightOS" (title includes the loaded show name).
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class UT {
  public delegate bool EP(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EP cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  static IntPtr _f = IntPtr.Zero;
  public static IntPtr Find() {
    _f = IntPtr.Zero;
    EnumWindows((h,l)=>{ if(IsWindowVisible(h)){ var sb=new StringBuilder(300); GetWindowText(h,sb,300);
      if(sb.ToString().StartsWith("LightOS", StringComparison.OrdinalIgnoreCase)){ _f=h; return false; } } return true; }, IntPtr.Zero);
    return _f;
  }
}
"@
$h = [UT]::Find()
if ($h -ne [IntPtr]::Zero) {
  # HWND_NOTOPMOST = -2, SWP_NOMOVE|SWP_NOSIZE = 0x0003
  [void][UT]::SetWindowPos($h, [IntPtr](-2), 0,0,0,0, 0x0003)
  "cleared topmost on $h"
} else { "LightOS window not found" }
