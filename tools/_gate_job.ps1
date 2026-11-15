# tools/_gate_job.ps1 - XPLAT-29 (b): Job-Objekt je Segment im Windows-Gate.
#
# Wird von tools/verify_segmented.ps1 per Dot-Sourcing geladen (wie
# _gate_webengine.ps1) - eine eigene Datei, damit die Win32-Teile nicht im
# Runner selbst stehen.
#
# WOFUER: Windows reisst Prozessbaeume nicht mit. Ein pytest-Segment, das
# endet (oder vom Runner wegen Zeitlimit beendet wird), hinterlaesst seine
# Kinder - QtWebEngineProcess, Hilfs-Pythons aus Tests - als Waisen. Gemessen
# am 01.09.2026: zwei python und ein QtWebEngineProcess aus dem VORIGEN Lauf
# hielten noch ein Log fest, der naechste Lauf endete vor Segment 1 (XPLAT-29
# (a) weicht seitdem aus). Und wer den Runner selbst abbricht (Stop-Process,
# Fenster zu), liess bisher JEDES laufende Segment samt Kindern stehen.
#
# WIE: jedes Segment startet in einem eigenen Job-Objekt mit
# KILL_ON_JOB_CLOSE, dasselbe Mittel wie XPLAT-24 fuer die DMX-Worker.
#   * Segment zu Ende  -> der Runner schliesst den Job, Windows beendet, was
#                         vom Segment noch laeuft (die Waisen).
#   * Runner stirbt    -> Windows schliesst seine Handles, also auch die Jobs,
#                         und beendet jedes noch laufende Segment samt Kindern.
#   * Fremde Prozesse  -> nie im Job. Die laufende App des Menschen, ein
#                         zweites Gate, ein Halter aus einem Test: alles, was
#                         dieser Runner nicht selbst gestartet hat, bleibt
#                         unberuehrt (COORDINATION.md: "Die laufende App
#                         gehoert dem Menschen").
#
# WARUM ANGEHALTEN STARTEN (CREATE_SUSPENDED) und nicht Start-Process: das
# venv-python.exe ist unter Windows nur ein Starter, der sofort das eigentliche
# Python als KIND startet. Wer den Starter erst nach Start-Process in den Job
# haengt, kommt zu spaet - das Kind laeuft dann schon ausserhalb, und mit ihm
# alles, was es startet. Angehalten gestartet ist der Prozess im Job, bevor er
# einen einzigen Befehl ausgefuehrt hat.
#
# Ein Fehler hier haelt das Gate NIE an: Start-ImJob liefert dann $null und
# der Runner startet das Segment wie vor XPLAT-29 (b) mit Start-Process - der
# Lauf zaehlt genauso, nur ohne Aufraeumen. Der Grund steht einmal in der
# Ausgabe.
#
# LIGHTOS_GATE_OHNE_JOB=1 schaltet es ab (Notausgang, falls ein Rechner mit
# verschachtelten Jobs Aerger macht) - nie still: die Bilanz sagt es an.

$script:gateJobHinweis = $null      # Grund, falls ohne Job-Objekt gestartet wurde
$script:gateJobBereit = $false

function Initialize-GateJob {
    if ($script:gateJobBereit) { return $true }
    if ($script:gateJobHinweis) { return $false }
    if ($env:LIGHTOS_GATE_OHNE_JOB) {
        $script:gateJobHinweis = "LIGHTOS_GATE_OHNE_JOB gesetzt"
        return $false
    }
    if ($env:OS -ne "Windows_NT") {
        $script:gateJobHinweis = "kein Windows"
        return $false
    }
    if ('LightOSGateJob' -as [type]) { $script:gateJobBereit = $true; return $true }
    try {
        Add-Type -ErrorAction Stop -TypeDefinition @'
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

public class LightOSGateStart
{
    public Process Proc;
    public bool ImJob;
    public int Fehler;
}

public static class LightOSGateJob
{
    [StructLayout(LayoutKind.Sequential)]
    public struct BasisGrenzen
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct IoZaehler
    {
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
        public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ErweiterteGrenzen
    {
        public BasisGrenzen Basis;
        public IoZaehler Io;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct Abrechnung
    {
        public long TotalUserTime, TotalKernelTime;
        public long ThisPeriodTotalUserTime, ThisPeriodTotalKernelTime;
        public uint TotalPageFaultCount, TotalProcesses, ActiveProcesses;
        public uint TotalTerminatedProcesses;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct Sicherheit
    {
        public int nLength;
        public IntPtr lpSecurityDescriptor;
        public int bInheritHandle;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct StartInfo
    {
        public int cb;
        public string lpReserved, lpDesktop, lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars;
        public int dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct ProzessInfo
    {
        public IntPtr hProcess, hThread;
        public int dwProcessId, dwThreadId;
    }

    const uint KILL_ON_JOB_CLOSE = 0x2000;
    const int KLASSE_ABRECHNUNG = 1;    // JobObjectBasicAccountingInformation
    const int KLASSE_ERWEITERT = 9;     // JobObjectExtendedLimitInformation
    const uint CREATE_SUSPENDED = 0x4;
    const int STARTF_USESTDHANDLES = 0x100;
    const uint GENERIC_WRITE = 0x40000000;
    const uint FILE_SHARE_READ_WRITE = 0x3;
    const uint CREATE_ALWAYS = 2;
    static readonly IntPtr UNGUELTIG = new IntPtr(-1);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern IntPtr CreateJobObjectW(IntPtr attribute, string name);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetInformationJobObject(IntPtr job, int klasse, ref ErweiterteGrenzen info, uint laenge);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool QueryInformationJobObject(IntPtr job, int klasse, out Abrechnung info, uint laenge, IntPtr rueck);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool AssignProcessToJobObject(IntPtr job, IntPtr prozess);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern IntPtr CreateFileW(string pfad, uint zugriff, uint teilen, ref Sicherheit sa,
                                     uint anlegen, uint attribute, IntPtr vorlage);
    [DllImport("kernel32.dll")]
    static extern IntPtr GetStdHandle(int welches);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool CreateProcessW(string programm, StringBuilder befehl, IntPtr pa, IntPtr ta,
                                      bool erben, uint flags, IntPtr umgebung, string ordner,
                                      ref StartInfo si, out ProzessInfo pi);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern int ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool TerminateProcess(IntPtr prozess, uint code);

    // Job mit KILL_ON_JOB_CLOSE; IntPtr.Zero, wenn es nicht geht. Das Handle
    // ist NICHT vererbbar - die Segmente halten ihren Job also nicht selbst
    // offen (sie starten mit Handle-Vererbung, wegen der Umleitung).
    public static IntPtr Anlegen()
    {
        IntPtr job = CreateJobObjectW(IntPtr.Zero, null);
        if (job == IntPtr.Zero) return IntPtr.Zero;
        ErweiterteGrenzen info = new ErweiterteGrenzen();
        info.Basis.LimitFlags = KILL_ON_JOB_CLOSE;
        if (!SetInformationJobObject(job, KLASSE_ERWEITERT, ref info,
                                     (uint)Marshal.SizeOf(typeof(ErweiterteGrenzen))))
        {
            CloseHandle(job);
            return IntPtr.Zero;
        }
        return job;
    }

    // Wie viele Prozesse im Job noch laufen; -1, wenn die Abfrage scheitert.
    public static int Aktive(IntPtr job)
    {
        if (job == IntPtr.Zero) return -1;
        Abrechnung a;
        if (!QueryInformationJobObject(job, KLASSE_ABRECHNUNG, out a,
                                       (uint)Marshal.SizeOf(typeof(Abrechnung)), IntPtr.Zero))
            return -1;
        return (int)a.ActiveProcesses;
    }

    // Letztes Handle zu -> Windows beendet alles, was noch im Job laeuft.
    public static void Schliessen(IntPtr job)
    {
        if (job != IntPtr.Zero) CloseHandle(job);
    }

    static string Zitieren(string a)
    {
        if (a.Length > 0 && a.IndexOfAny(new char[] { ' ', '\t', '"' }) < 0) return a;
        StringBuilder sb = new StringBuilder("\"");
        int striche = 0;
        foreach (char c in a)
        {
            if (c == '\\') { striche++; continue; }
            if (c == '"') { sb.Append('\\', striche * 2 + 1); sb.Append('"'); striche = 0; continue; }
            sb.Append('\\', striche); striche = 0; sb.Append(c);
        }
        sb.Append('\\', striche * 2);
        sb.Append('"');
        return sb.ToString();
    }

    static IntPtr Ausgabedatei(string pfad)
    {
        Sicherheit sa = new Sicherheit();
        sa.nLength = Marshal.SizeOf(typeof(Sicherheit));
        sa.bInheritHandle = 1;
        IntPtr h = CreateFileW(pfad, GENERIC_WRITE, FILE_SHARE_READ_WRITE, ref sa,
                               CREATE_ALWAYS, 0x80, IntPtr.Zero);
        if (h == UNGUELTIG)
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), pfad);
        return h;
    }

    // Startet `programm args` angehalten, mit stdout/stderr in die Dateien,
    // haengt ihn in den Job (falls job != Zero) und laesst ihn erst dann los.
    // Wirft nur, wenn KEIN Prozess weiterlaeuft - dann darf der Aufrufer neu
    // starten, ohne ein Segment doppelt zu fahren.
    public static LightOSGateStart Starten(string programm, string[] args, string ordner,
                                           string ausgabe, string fehler, IntPtr job)
    {
        StringBuilder befehl = new StringBuilder(Zitieren(programm));
        foreach (string a in args) { befehl.Append(' '); befehl.Append(Zitieren(a)); }

        IntPtr hOut = Ausgabedatei(ausgabe);
        IntPtr hErr = IntPtr.Zero;
        ProzessInfo pi;
        try
        {
            hErr = Ausgabedatei(fehler);
            StartInfo si = new StartInfo();
            si.cb = Marshal.SizeOf(typeof(StartInfo));
            si.dwFlags = STARTF_USESTDHANDLES;
            si.hStdInput = GetStdHandle(-10);
            si.hStdOutput = hOut;
            si.hStdError = hErr;
            if (!CreateProcessW(programm, befehl, IntPtr.Zero, IntPtr.Zero, true, CREATE_SUSPENDED,
                                IntPtr.Zero, ordner, ref si, out pi))
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), programm);
        }
        finally
        {
            CloseHandle(hOut);
            if (hErr != IntPtr.Zero) CloseHandle(hErr);
        }

        LightOSGateStart erg = new LightOSGateStart();
        try
        {
            erg.Proc = Process.GetProcessById(pi.dwProcessId);
            // Handle cachen, solange der Prozess sicher lebt: sonst liefert
            // ExitCode unter PS 5.1 nach dem Ende nur $null (s. Start-Segment).
            if (erg.Proc.Handle == IntPtr.Zero) throw new InvalidOperationException("kein Prozess-Handle");
            if (job != IntPtr.Zero)
            {
                erg.ImJob = AssignProcessToJobObject(job, pi.hProcess);
                if (!erg.ImJob) erg.Fehler = Marshal.GetLastWin32Error();
            }
            if (ResumeThread(pi.hThread) == -1)
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "ResumeThread");
        }
        catch
        {
            TerminateProcess(pi.hProcess, 1);
            throw;
        }
        finally
        {
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
        }
        return erg;
    }
}
'@
        $script:gateJobBereit = $true
        return $true
    }
    catch {
        $script:gateJobHinweis = "Add-Type: $($_.Exception.Message)"
        return $false
    }
}

# Startet ein Segment in einem eigenen Job. Rueckgabe @{ Proc; Job } oder
# $null - dann startet der Aufrufer wie bisher (und es lief KEIN Prozess an).
# Job ist [IntPtr]::Zero, wenn der Prozess laeuft, aber nicht in den Job kam.
function Start-ImJob([string]$Datei, [string[]]$Argumente, [string]$Ordner,
                     [string]$Ausgabe, [string]$Fehler) {
    if (-not (Initialize-GateJob)) { return $null }
    $job = [LightOSGateJob]::Anlegen()
    if ($job -eq [IntPtr]::Zero) {
        if (-not $script:gateJobHinweis) { $script:gateJobHinweis = "CreateJobObject scheiterte" }
        $script:gateJobBereit = $false
        return $null
    }
    try {
        $erg = [LightOSGateJob]::Starten($Datei, $Argumente, $Ordner, $Ausgabe, $Fehler, $job)
    }
    catch {
        [LightOSGateJob]::Schliessen($job)
        if (-not $script:gateJobHinweis) { $script:gateJobHinweis = "Start: $($_.Exception.Message)" }
        $script:gateJobBereit = $false
        return $null
    }
    if (-not $erg.ImJob) {
        # Laeuft, aber ausserhalb: Job wieder zu, ohne Wirkung (er ist leer).
        [LightOSGateJob]::Schliessen($job)
        $job = [IntPtr]::Zero
        if (-not $script:gateJobHinweis) {
            $script:gateJobHinweis = "AssignProcessToJobObject: Win32-Fehler $($erg.Fehler)"
        }
    }
    return @{ Proc = $erg.Proc; Job = $job }
}

# Schliesst den Job eines Segments. Rueckgabe: wie viele Prozesse dabei noch
# liefen (die Waisen, die Windows jetzt beendet), -1 ohne Job.
function Close-SegmentJob($rec) {
    if (-not $rec.Job -or $rec.Job -eq [IntPtr]::Zero) { return -1 }
    $noch = [LightOSGateJob]::Aktive($rec.Job)
    [LightOSGateJob]::Schliessen($rec.Job)
    $rec.Job = [IntPtr]::Zero
    return $noch
}
