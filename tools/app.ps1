<#
.SYNOPSIS
  LightOS App-Treiber — App starten/stoppen/warten/screenshotten aus EINEM Skript.

.DESCRIPTION
  Konsolidiert die verstreuten Ad-hoc-UI-Drive-Skripte (docs/_walkthrough/lo.ps1,
  docs/tutorial_matrix/_ui.ps1 / _cap.ps1 / _fg.ps1) zu einem sauberen Werkzeug mit
  klaren Subkommandos. Nutzt die dort bewaehrten Mechaniken:
    - App-Start ueber die venv:  venv\Scripts\pythonw.exe main.py --touch
    - App-Stop:  pythonw/python-Prozess killen, dessen Kommandozeile main.py enthaelt
    - Fenster finden per Win32 EnumWindows (Titel "LightOS", Besitzer = python-Prozess),
      damit Datei-Explorer/Konsole mit demselben Titel nicht faelschlich getroffen werden
    - Vordergrund + TOPMOST erzwingen (AttachThreadInput/SetWindowPos), DPI-aware
    - Screenshot per GDI CopyFromScreen (computer-use sieht das Qt-Fenster nicht)

  Repo-Root wird relativ zum Skript aufgeloest ($PSScriptRoot\..), d.h. das innere
  Projekt, in dem main.py + venv liegen.

.PARAMETER Command
  Subkommando:
    start          App via venv starten (pythonw main.py --touch), Arbeitsverz. = Repo-Root.
    stop           Laufende App(s) beenden (pythonw/python mit main.py in der Cmdline).
    restart        stop + start.
    wait           Auf das LightOS-Fenster warten (Bereitschaft). Timeout via -TimeoutSec.
    shot <Path>    Screenshot des gesamten virtuellen Bildschirms als PNG nach <Path>.
                   Optional -Width skaliert die Breite; -X -Y -W -H schneidet einen Bereich zu.
    fg             LightOS in den Vordergrund + TOPMOST zwingen (vor jeder Aufnahme).
    untop          TOPMOST-Flag wieder loeschen (am Ende einer Session).

.PARAMETER TimeoutSec
  Maximale Wartezeit fuer 'wait' (und implizit beim 'restart'/'start' auf Bereitschaft warten,
  wenn -Wait gesetzt ist). Default 30 Sekunden.

.PARAMETER Width
  Fuer 'shot': Ziel-Breite in Pixeln; skaliert proportional herunter (0 = volle Aufloesung).

.PARAMETER X
  Fuer 'shot': linke Kante des Crop-Bereichs (physische Pixel).

.PARAMETER Y
  Fuer 'shot': obere Kante des Crop-Bereichs (physische Pixel).

.PARAMETER W
  Fuer 'shot': Breite des Crop-Bereichs (0 = ganzer Bildschirm).

.PARAMETER H
  Fuer 'shot': Hoehe des Crop-Bereichs (0 = ganzer Bildschirm).

.PARAMETER Wait
  Fuer 'start'/'restart': nach dem Start auf das Fenster warten (bis -TimeoutSec).

.EXAMPLE
  tools\app.ps1 restart -Wait
  Beendet eine laufende App, startet sie neu und wartet auf das Fenster.

.EXAMPLE
  tools\app.ps1 wait -TimeoutSec 45

.EXAMPLE
  tools\app.ps1 shot docs\img\live.png -Width 1400

.EXAMPLE
  tools\app.ps1 shot docs\img\pad.png -X 90 -Y 430 -W 260 -H 200

.NOTES
  Ersetzt (konsolidiert) die Alt-Toolsets docs/_walkthrough/lo.ps1 und
  docs/tutorial_matrix/_ui.ps1 / _cap.ps1 / _fg.ps1 / _untop.ps1. Die Alt-Skripte bleiben
  vorerst als Referenz erhalten. Keine echte App fuer den Selbsttest noetig — reines PS-Tooling.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet('start', 'stop', 'restart', 'wait', 'shot', 'fg', 'untop')]
  [string]$Command,

  [Parameter(Position = 1)]
  [string]$Path,

  [int]$TimeoutSec = 30,
  [int]$Width = 0,
  [int]$X = 0,
  [int]$Y = 0,
  [int]$W = 0,
  [int]$H = 0,
  [switch]$Wait
)

# --- Win32 helper (Fenster finden / Vordergrund / DPI) -----------------------------------
# Uebernommen aus der bewaehrten LO-Klasse in docs/_walkthrough/lo.ps1: nur das VISIBLE
# Fenster mit Titel "LightOS"/"LightOS ..." UND python-Besitzer wird als App-Fenster gewertet.
Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices;
public class LOApp {
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
}
"@
[void][LOApp]::SetProcessDPIAware()
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Get-AppProcesses {
  # pythonw/python-Prozesse, deren Kommandozeile main.py enthaelt (bewaehrte Kill-Heuristik).
  Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'main\.py' }
}

function Start-App {
  $py = Join-Path $RepoRoot 'venv\Scripts\pythonw.exe'
  $mainPy = Join-Path $RepoRoot 'main.py'
  if (-not (Test-Path $py)) { Write-Output "FEHLER: venv-pythonw nicht gefunden: $py"; return }
  if (-not (Test-Path $mainPy)) { Write-Output "FEHLER: main.py nicht gefunden: $mainPy"; return }
  Start-Process -FilePath $py -ArgumentList 'main.py', '--touch' -WorkingDirectory $RepoRoot | Out-Null
  Write-Output "gestartet: $py main.py --touch (cwd=$RepoRoot)"
}

function Stop-App {
  $procs = @(Get-AppProcesses)
  if ($procs.Count -eq 0) { Write-Output 'keine laufende LightOS-App gefunden'; return }
  foreach ($p in $procs) {
    try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; Write-Output "gestoppt PID=$($p.ProcessId)" }
    catch { Write-Output "konnte PID=$($p.ProcessId) nicht stoppen: $($_.Exception.Message)" }
  }
}

function Wait-App([int]$timeoutSec) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    $h = [LOApp]::Find()
    if ($h -ne [IntPtr]::Zero) { Write-Output "bereit: hwnd=$h title='$([LOApp]::Title)'"; return $true }
    Start-Sleep -Milliseconds 300
  }
  Write-Output "TIMEOUT: LightOS-Fenster nach ${timeoutSec}s nicht gefunden"
  return $false
}

function Save-Shot([int]$sx, [int]$sy, [int]$sw, [int]$sh, [string]$outPath, [int]$targetW) {
  $bmp = New-Object System.Drawing.Bitmap($sw, $sh)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($sx, $sy, 0, 0, (New-Object System.Drawing.Size($sw, $sh)))
  if ($targetW -gt 0 -and $targetW -lt $sw) {
    $th = [int]($sh * $targetW / $sw)
    $sb = New-Object System.Drawing.Bitmap($targetW, $th)
    $sg = [System.Drawing.Graphics]::FromImage($sb)
    $sg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $sg.DrawImage($bmp, 0, 0, $targetW, $th)
    $sb.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png); $sg.Dispose(); $sb.Dispose()
    Write-Output "saved $outPath (${targetW}x${th}, from ${sw}x${sh})"
  } else {
    $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Output "saved $outPath (${sw}x${sh})"
  }
  $g.Dispose(); $bmp.Dispose()
}

switch ($Command) {
  'start'   { Start-App; if ($Wait) { [void](Wait-App $TimeoutSec) } }
  'stop'    { Stop-App }
  'restart' { Stop-App; Start-Sleep -Milliseconds 600; Start-App; if ($Wait) { [void](Wait-App $TimeoutSec) } }
  'wait'    { [void](Wait-App $TimeoutSec) }
  'fg'      {
    $h = [LOApp]::Force($true); Start-Sleep -Milliseconds 250
    $r = New-Object LOApp+RECT; [void][LOApp]::GetWindowRect($h, [ref]$r)
    Write-Output "fg hwnd=$h title='$([LOApp]::Title)' rect=$($r.L),$($r.T),$($r.R),$($r.B) $($r.R-$r.L)x$($r.B-$r.T)"
  }
  'untop'   { [LOApp]::Untop(); Write-Output 'untopped' }
  'shot'    {
    if (-not $Path) { Write-Output 'FEHLER: shot braucht einen Ziel-Pfad'; break }
    if ($W -gt 0 -and $H -gt 0) {
      Save-Shot $X $Y $W $H $Path $Width
    } else {
      $b = [System.Windows.Forms.SystemInformation]::VirtualScreen
      Save-Shot $b.X $b.Y $b.Width $b.Height $Path $Width
    }
  }
  default   { Write-Output "unbekanntes Kommando: $Command" }
}
