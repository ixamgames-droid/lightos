"""XPLAT-24 — der DMX-Worker ueberlebt den harten Tod der App nicht.

Nachgestellt wie am Rig: die App wird hart beendet (Task-Manager „Task
beenden“ = ``TerminateProcess``, hier ``os.kill``), mit einem ECHTEN
:class:`EnttecProcessProxy` und echten Prozessen.

* Der normale Worker beendet sich seit OUT-59 ueber die Handle-Wache (gemessen
  2026-10-08 auf dem Windows-ARM-PC: 0,10 s nach dem Kill). Der erste Test
  haelt das fest - der OUT-59-Test nutzt nur die Wache allein, ohne Proxy und
  ohne harten Kill.
* Die Wache prueft aber nur, wer in seiner Schleife ankommt. Ein Worker, der im
  Treiber haengt (genau der Fall, fuer den die Prozess-Isolation gebaut ist),
  und ein Worker, dessen App stirbt, bevor er das Handle oeffnen konnte, blieben
  als Waise am COM-Port. Dagegen haengt der Proxy jeden Worker unter Windows in
  ein Job-Objekt mit ``KILL_ON_JOB_CLOSE``: stirbt die App, schliesst Windows
  das Job-Handle und beendet den Worker - egal, was er gerade tut.
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Die App: baut den Proxy, meldet ihre eigene PID (unter Windows startet
# venv\Scripts\python.exe einen Basis-Interpreter als Kind - getoetet wird der
# Prozess, der den Proxy haelt) und die Worker-PID, dann wartet sie.
_APP = r"""
import multiprocessing as mp, os, sys, time
sys.path.insert(0, sys.argv[1])
from src.core.dmx.serial_process import EnttecProcessProxy

def haengt():
    # Worker, der seine Schleife nie erreicht (Treiber-Haenger im Senden).
    time.sleep(600)

if __name__ == "__main__":
    modus = sys.argv[3]
    fabrik = None
    if modus == "haengt":
        ctx = mp.get_context("spawn")
        fabrik = lambda: ctx.Process(target=haengt, daemon=True)
    p = EnttecProcessProxy("COM250", _process_factory=fabrik)
    ende = time.time() + 20
    while not p.is_open() and time.time() < ende:
        time.sleep(0.05)
    time.sleep(1.0)       # Worker ist in seiner Schleife bzw. im Haenger
    with open(sys.argv[2] + ".tmp", "w") as f:
        f.write(f"{os.getpid()} {p._proc.pid}")
    os.replace(sys.argv[2] + ".tmp", sys.argv[2])
    time.sleep(120)
"""


def _lebt(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        k32 = ctypes.WinDLL("kernel32")
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        k32.WaitForSingleObject.restype = ctypes.c_uint32
        k32.CloseHandle.argtypes = (ctypes.c_void_p,)
        h = k32.OpenProcess(0x00100000, False, pid)        # SYNCHRONIZE
        if not h:
            return False
        try:
            return k32.WaitForSingleObject(h, 0) == 0x102   # WAIT_TIMEOUT
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:   # Zombie zaehlt als tot
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


def _hart_beenden(pid: int):
    # Windows: os.kill ruft TerminateProcess - wie Task-Manager „Task beenden“.
    os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))


class WorkerStirbtMitDerApp(unittest.TestCase):

    def _app_starten_und_toeten(self, modus: str) -> tuple[int, float | None]:
        tmp = tempfile.mkdtemp(prefix="xplat24_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        skript = os.path.join(tmp, "app.py")
        pids = os.path.join(tmp, "pids.txt")
        with open(skript, "w", encoding="utf-8") as f:
            f.write(_APP)
        env = dict(os.environ, PYTHONPATH=REPO)
        env.pop("LIGHTOS_SERIAL_INPROC", None)
        start = subprocess.Popen([sys.executable, skript, REPO, pids, modus],
                                 cwd=REPO, env=env)
        self.addCleanup(lambda: start.poll() is None and start.kill())
        ende = time.time() + 40
        while not os.path.exists(pids) and time.time() < ende:
            self.assertIsNone(start.poll(), "App-Prozess endete vor dem Bericht")
            time.sleep(0.1)
        self.assertTrue(os.path.exists(pids), "App hat keine PIDs gemeldet")
        with open(pids, encoding="utf-8") as f:
            app_pid, worker_pid = map(int, f.read().split())
        # Aufraeumen auch im Fehlerfall: keine Waise aus dem Test selbst.
        self.addCleanup(lambda: _lebt(worker_pid) and _hart_beenden(worker_pid))
        self.assertTrue(_lebt(worker_pid), "Worker lief vor dem Kill nicht")

        _hart_beenden(app_pid)
        t0 = time.time()
        while time.time() - t0 < 5.0:
            if not _lebt(worker_pid):
                try:
                    start.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
                return worker_pid, time.time() - t0
            time.sleep(0.05)
        return worker_pid, None

    def test_echter_worker_stirbt_mit_hart_beendeter_app(self):
        _, dauer = self._app_starten_und_toeten("normal")
        self.assertIsNotNone(dauer, "Worker lebt 5 s nach dem harten Tod der App noch (Waise)")

    @unittest.skipUnless(os.name == "nt", "Job-Objekt gibt es nur unter Windows")
    def test_haengender_worker_stirbt_mit_hart_beendeter_app(self):
        _, dauer = self._app_starten_und_toeten("haengt")
        self.assertIsNotNone(
            dauer, "Ein haengender Worker ueberlebt die App - er haelt den COM-Port, "
                   "die naechste App bekommt keine Ausgabe")


class JobObjekt(unittest.TestCase):

    def test_ausserhalb_von_windows_kein_job(self):
        from src.core.dmx import serial_process as sp
        if os.name != "nt":
            self.assertIsNone(sp._kill_job_anlegen())

    @unittest.skipUnless(os.name == "nt", "Windows-Pfad")
    def test_proxy_ohne_echten_prozess_bleibt_heil(self):
        """Test-Fabriken liefern Attrappen ohne Handle: Job-Zuordnung darf dann
        still entfallen, der Proxy muss trotzdem arbeiten und schliessen."""
        from src.core.dmx import serial_process as sp

        class _Attrappe:
            pid = 0
            def start(self):
                pass
            def is_alive(self):
                return True
            def join(self, timeout=None):
                pass

        p = sp.EnttecProcessProxy("COM250", _process_factory=_Attrappe)
        self.assertTrue(p.is_open())
        p.close()
        p.close()   # idempotent, auch fuer das Job-Handle
        self.assertIsNone(p._job)


if __name__ == "__main__":
    unittest.main()
