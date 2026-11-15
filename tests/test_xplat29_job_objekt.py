"""XPLAT-29 (b): Kinder eines Segments ueberleben weder ihr Segment noch den Runner.

**Der Befund (01.09.2026).** Nach einem Gate-Lauf lebten noch zwei ``python``
und ein ``QtWebEngineProcess`` aus dem VORIGEN Lauf und hielten ein Log fest;
der naechste Start endete vor Segment 1. Windows reisst Prozessbaeume nicht mit
(dieselbe Wurzel wie XPLAT-24). Teil (a) laesst den Runner seitdem ausweichen
statt zu sterben; die Waisen selbst blieben.

**Was (b) aendert.** ``tools/verify_segmented.ps1`` startet jedes Segment in
einem eigenen Job-Objekt mit ``KILL_ON_JOB_CLOSE`` (``tools/_gate_job.ps1``):
endet das Segment, beendet der Runner, was davon noch laeuft; stirbt der
Runner selbst, schliesst Windows die Jobs und beendet alle laufenden Segmente
samt Kindern.

★ **Warum angehalten gestartet wird.** Das ``python.exe`` im venv ist unter
Windows nur ein Starter, der sofort das eigentliche Python als Kind startet.
Ein Job, der erst nach ``Start-Process`` zugeordnet wird, kommt zu spaet - die
Tests hier wuerden das als ueberlebendes Kind zeigen.

**Die Abgrenzung bleibt:** was der Runner nicht selbst gestartet hat, fasst er
nicht an - die laufende App des Menschen nicht, einen Halter aus einem Test
nicht (dazu auch ``test_xplat29_aufraeumen_stirbt_nicht.py``).
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tools" / "verify_segmented.ps1"

_IST_WINDOWS = sys.platform == "win32"
_GRUND = ("Job-Objekte gibt es nur unter Windows, und verify_segmented.ps1 ist "
          "das Windows-Gate - auf Linux faehrt verify_segmented.sh")

#: Wie XPLAT-27/29(a)/31: dieser Test startet selbst einen Segment-Runner. Im
#: Volllauf waere das ein Gate IM Gate (QA-53).
_IM_SEGMENT = bool(os.environ.get("LIGHTOS_IM_SEGMENT"))
_SEGMENT_GRUND = (
    "startet selbst einen Segment-Runner - im Volllauf waere das ein Gate IM "
    "Gate (QA-53). Gezielter Nachweis: "
    ".\\tools\\verify_loop.ps1 tests\\test_xplat29_job_objekt.py")

#: Die Probe-Testdatei: startet ein Kind, das sie selbst nie beendet (wie ein
#: QtWebEngineProcess, der sein pytest ueberlebt), schreibt dessen PID, die
#: eigene und die ihres Starters (venv-python.exe) in eine Datei und wartet
#: dann XPLAT29_DAUER Sekunden. Das Kind wird
#: direkt mit dem Basis-Interpreter gestartet - ohne venv-Starter ist es EIN
#: Prozess, dessen Ende sich eindeutig pruefen laesst.
PROBE = '''\
import os
import subprocess
import sys
import time
from pathlib import Path

_KINDER = []


def test_hinterlaesst_ein_kind():
    exe = getattr(sys, "_base_executable", None) or sys.executable
    kind = subprocess.Popen([exe, "-c", "import time; time.sleep(600)"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    _KINDER.append(kind)
    Path(os.environ["XPLAT29_PID_DATEI"]).write_text(
        f"{kind.pid} {os.getpid()} {os.getppid()}", encoding="utf-8")
    time.sleep(float(os.environ["XPLAT29_DAUER"]))
'''

_SYNCHRONIZE = 0x00100000
_PROCESS_TERMINATE = 0x0001
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WAIT_OBJECT_0 = 0

if _IST_WINDOWS:
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _k32.WaitForSingleObject.restype = wintypes.DWORD
    _k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    _k32.TerminateProcess.restype = wintypes.BOOL
    _k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
@unittest.skipIf(_IM_SEGMENT, _SEGMENT_GRUND)
class JobObjektTest(unittest.TestCase):

    def setUp(self):
        # ignore_cleanup_errors: im roten Lauf stirbt ein Segment erst im
        # tearDown, und Windows gibt seine Logdatei einen Moment spaeter frei.
        self._tmp = tempfile.TemporaryDirectory(prefix="lightos_xplat29b_",
                                                ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        # Leere pytest.ini: pinnt das rootdir des inneren Laufs auf diesen Ordner.
        (self.tmp / "pytest.ini").write_text("", encoding="utf-8")
        self.probe = self.tmp / "test_probe_kind.py"
        self.probe.write_text(PROBE, encoding="utf-8")
        self.pid_datei = self.tmp / "pids.txt"
        self.out = self.tmp / "out"
        self.out.mkdir()
        self.ausgabe = self.tmp / "runner.txt"
        self.handles: list[int] = []
        self.runner: subprocess.Popen | None = None
        self.fremd: subprocess.Popen | None = None

    def tearDown(self):
        # Ohne Job-Objekt (roter Lauf, Gegenprobe) leben die Prozesse noch -
        # sie duerfen den naechsten Test nicht stoeren.
        for h in self.handles:
            _k32.TerminateProcess(h, 1)
        for h in self.handles:
            _k32.WaitForSingleObject(h, 10_000)
            _k32.CloseHandle(h)
        for p in (self.runner, self.fremd):
            if p is not None and p.poll() is None:
                p.kill()
                p.wait(timeout=30)
        self._tmp.cleanup()

    # -- Hilfen --------------------------------------------------------------

    def _starte_runner(self, dauer: float, ohne_job: bool = False) -> subprocess.Popen:
        umgebung = dict(os.environ)
        umgebung["LIGHTOS_SEG_OUT"] = str(self.out)
        umgebung["LIGHTOS_SHOW_DB"] = str(self.tmp / "kind_show.db")
        umgebung["QT_QPA_PLATFORM"] = "offscreen"
        umgebung["XPLAT29_PID_DATEI"] = str(self.pid_datei)
        umgebung["XPLAT29_DAUER"] = str(dauer)
        umgebung.pop("LIGHTOS_IM_SEGMENT", None)
        umgebung.pop("LIGHTOS_GATE_OHNE_JOB", None)
        if ohne_job:
            umgebung["LIGHTOS_GATE_OHNE_JOB"] = "1"
        # Ausgabe in eine DATEI, nicht in eine Pipe: Segmente erben die Handles
        # des Runners - ein ueberlebendes Segment hielte eine Pipe offen, und
        # das Auslesen hinge so lange wie es.
        with open(self.ausgabe, "wb") as ziel:
            self.runner = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(RUNNER), "-j", "1", str(self.probe)],
                cwd=str(REPO), env=umgebung, stdout=ziel, stderr=subprocess.STDOUT)
        return self.runner

    def _text(self) -> str:
        return self.ausgabe.read_bytes().decode("utf-8", "replace")

    def _oeffne(self, pid: int) -> int:
        h = _k32.OpenProcess(_SYNCHRONIZE | _PROCESS_TERMINATE
                             | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            self.fail(f"Prozess {pid} liess sich nicht oeffnen "
                      f"(Win32-Fehler {ctypes.get_last_error()})")
        self.handles.append(h)
        return h

    def _warte_auf_pids(self) -> tuple[int, int]:
        """Handles von Kind und Segment, sobald die Probe ihre PIDs schrieb.

        Die Handles werden SOFORT geoeffnet, solange alle sicher leben - so
        kann eine wiederverwendete PID das Ergebnis nicht verfaelschen. Der
        Starter des Segments wird nur fuers Aufraeumen mitgenommen."""
        ende = time.monotonic() + 120
        while time.monotonic() < ende:
            if self.pid_datei.exists():
                text = self.pid_datei.read_text(encoding="utf-8").split()
                if len(text) == 3:
                    kind, segment, _starter = (self._oeffne(int(t)) for t in text)
                    return kind, segment
            if self.runner is not None and self.runner.poll() is not None:
                self.fail("der Runner endete, bevor die Probe lief:\n"
                          + self._text()[-1500:])
            time.sleep(0.05)
        self.fail("die Probe hat nie ihre PIDs geschrieben:\n" + self._text()[-1500:])

    @staticmethod
    def _endet(h: int, sekunden: float) -> bool:
        return _k32.WaitForSingleObject(h, int(sekunden * 1000)) == _WAIT_OBJECT_0

    # -- Nachweise -----------------------------------------------------------

    def test_ein_kind_ueberlebt_sein_segment_nicht(self):
        """★★ Der Kern: die Waise aus dem Befund vom 01.09.2026.

        Das Segment ist gruen und endet normal, sein Kind laeuft weiter. Vor
        XPLAT-29 (b) lebte es danach unbegrenzt (hier: 600 s) - und mit ihm
        jede Datei, die es offen hielt."""
        runner = self._starte_runner(dauer=2)
        kind, _ = self._warte_auf_pids()
        rc = runner.wait(timeout=600)
        ausgabe = self._text()
        self.assertEqual(0, rc, ausgabe[-1500:])
        self.assertRegex(ausgabe, r"1/1 Segmente gruen", ausgabe[-1500:])
        self.assertTrue(
            self._endet(kind, 10),
            "das Kind des Segments lebt nach dem Lauf noch - genau die Waise "
            f"aus XPLAT-29:\n{ausgabe[-1500:]}")
        self.assertRegex(
            ausgabe, r"hinterliessen laufende Kindprozesse",
            "der Runner hat die Waise beendet, ohne es zu sagen - dann sieht "
            f"niemand, welche Datei sie hinterlaesst:\n{ausgabe[-1500:]}")
        self.assertIn(self.probe.name, ausgabe, ausgabe[-1500:])

    def test_ein_abgebrochener_runner_laesst_nichts_stehen(self):
        """★★ Der zweite Weg zu Waisen: der Runner selbst stirbt.

        Wer einen Gate-Lauf abbricht (Stop-Process, Konsole zu, Absturz),
        liess bisher jedes laufende Segment samt Kindern stehen - mitten im
        Test, mit allem, was es offen hielt. Jetzt schliesst Windows mit dem
        Runner die Jobs und beendet beides.

        Und die Abgrenzung im selben Lauf: ein Prozess, den NICHT der Runner
        gestartet hat (wie die App des Menschen), lebt danach weiter."""
        exe = getattr(sys, "_base_executable", None) or sys.executable
        self.fremd = subprocess.Popen(
            [exe, "-c", "import time; time.sleep(600)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        runner = self._starte_runner(dauer=300)
        kind, segment = self._warte_auf_pids()

        runner.kill()                    # TerminateProcess - nur der Runner, kein Baum
        runner.wait(timeout=30)

        self.assertTrue(
            self._endet(segment, 15),
            "das Segment laeuft weiter, obwohl sein Runner tot ist:\n"
            + self._text()[-1500:])
        self.assertTrue(
            self._endet(kind, 15),
            "das Kind des Segments laeuft weiter, obwohl der Runner tot ist")
        self.assertIsNone(
            self.fremd.poll(),
            "ein Prozess, den der Runner NICHT gestartet hat, wurde beendet - "
            "der Runner darf nur seine eigenen Kinder raeumen (die laufende App "
            "des Menschen haelt selbst Chromium-Kinder)")

    def test_ohne_job_objekt_laeuft_das_gate_trotzdem(self):
        """★ Gegenprobe und Rueckfall in einem.

        Mit ``LIGHTOS_GATE_OHNE_JOB`` startet der Runner wie vor XPLAT-29 (b).
        Der Lauf muss genauso gruen werden - ein Fehler beim Job darf das Gate
        nie anhalten - und es SAGEN, weil er nicht mehr aufraeumt. Dass das
        Kind dann ueberlebt, belegt zugleich: im ersten Test war es der Job,
        nicht irgendein anderer Mechanismus, der es beendet hat."""
        runner = self._starte_runner(dauer=0, ohne_job=True)
        kind, _ = self._warte_auf_pids()
        rc = runner.wait(timeout=600)
        ausgabe = self._text()
        self.assertEqual(0, rc, ausgabe[-1500:])
        self.assertRegex(ausgabe, r"1/1 Segmente gruen", ausgabe[-1500:])
        self.assertIn("ohne Job-Objekt", ausgabe,
                      "der Rueckfall ist still - dann haelt man das Gate fuer "
                      f"aufgeraeumt:\n{ausgabe[-1500:]}")
        self.assertFalse(self._endet(kind, 2),
                         "ohne Job-Objekt ist das Kind trotzdem gestorben - "
                         "dann prueft der erste Test nicht den Job")


#: QA-120: startet EIN Segment ueber ``Start-ImJob``, nachdem der "Runner" sein
#: eigenes stdin unvererbbar gemacht hat (so kann es ein Runner ohne Konsole
#: oder mit fremder Umleitung vorfinden).
_EINGABE_SKRIPT = r'''
param($GateJob, $Py, $Kind, $Ordner)
. $GateJob
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Qa120Handle {
    [DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int n);
    [DllImport("kernel32.dll")] public static extern bool SetHandleInformation(IntPtr h, uint maske, uint flags);
}
"@
if (-not [Qa120Handle]::SetHandleInformation([Qa120Handle]::GetStdHandle(-10), 1, 0)) {
    "SETHANDLE gescheitert"; exit 4
}
if (-not (Initialize-GateJob)) { "KEIN JOB: $script:gateJobHinweis"; exit 3 }
$rec = Start-ImJob $Py @($Kind) $Ordner (Join-Path $Ordner 'aus.txt') (Join-Path $Ordner 'fehler.txt')
if (-not $rec) { "START gescheitert: $script:gateJobHinweis"; exit 5 }
[void]$rec.Proc.WaitForExit(60000)
[void](Close-SegmentJob $rec)
"FERTIG"
'''

#: Das Segment: prueft sein stdin, ohne zu blockieren (gelesen wird nur NUL).
_EINGABE_KIND = '''\
import ctypes, msvcrt, sys
if sys.stdin is None:
    print("STDIN fehlt")
else:
    typ = ctypes.windll.kernel32.GetFileType(msvcrt.get_osfhandle(0))
    print("STDIN leer" if typ == 2 and sys.stdin.buffer.read(1) == b"" else f"STDIN Typ {typ}")
'''


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
class SegmentEingabeTest(unittest.TestCase):
    """QA-120: das stdin eines Segments ist ein gueltiges, leeres NUL.

    Vorher bekam das Segment das stdin-Handle des Runners (``GetStdHandle``).
    Ist es nicht vererbbar, steht im Segment nur eine Handle-Nummer ohne Objekt
    (Python: ``sys.stdin`` fehlt) - oder, schlimmer, eine fremde Datei."""

    def test_stdin_ist_nul_auch_wenn_das_des_runners_nicht_vererbbar_ist(self):
        with tempfile.TemporaryDirectory(prefix="lightos_qa120_",
                                         ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            (tmp / "start.ps1").write_text(_EINGABE_SKRIPT, encoding="ascii")
            (tmp / "kind.py").write_text(_EINGABE_KIND, encoding="ascii")
            exe = getattr(sys, "_base_executable", None) or sys.executable
            r = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(tmp / "start.ps1"), str(REPO / "tools" / "_gate_job.ps1"),
                 exe, str(tmp / "kind.py"), str(tmp)],
                stdin=subprocess.PIPE, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180)
            self.assertIn("FERTIG", r.stdout, r.stdout[-1500:] + r.stderr[-1500:])
            aus = (tmp / "aus.txt").read_text(encoding="utf-8", errors="replace")
            fehler = (tmp / "fehler.txt").read_text(encoding="utf-8", errors="replace")
            self.assertEqual("STDIN leer", aus.strip(), aus + fehler[-1500:])


if __name__ == "__main__":
    unittest.main()
