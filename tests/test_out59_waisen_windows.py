"""OUT-59 — die Waisen-Wache des Serial-Workers greift auch unter Windows.

Befund (Sitzung B, Windows-Rig-PC, 03.10.2026): nach zwei App-Laeufen liefen
vier ``spawn_main``-Worker ohne Eltern weiter; einer hatte COM3 geoeffnet,
sobald der Enttec steckte, und der naechste Start meldete „COM3 ist bereits von
einem anderen Prozess geoeffnet“ — die Ausgabe lief nicht an. Ursache: OUT-53
erkennt den Tod des Parents ueber ``os.getppid()``; unter Windows aendert sich
dieser Wert nie (gemessen: vor und nach dem Tod dieselbe PID).

Der Test faehrt das mit ECHTEN Prozessen: ein Zwischenprozess startet ein Kind,
das ``_eltern_wache`` benutzt, und beendet sich dann selbst. Das Kind muss den
Tod innerhalb weniger Sekunden bemerken — auf jeder Plattform.
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Wie im Produktivpfad: der Worker entsteht ueber multiprocessing (spawn) —
# unter Windows startet das den BASIS-Interpreter direkt. Ein Kind ueber
# subprocess + venv-python.exe saehe dagegen seinen eigenen venv-Starter als
# Parent, und der lebt, solange das Kind lebt.
_ELTERN = r"""
import multiprocessing as mp, os, sys, time
sys.path.insert(0, sys.argv[1])

def kind(out):
    from src.core.dmx.serial_process import _eltern_wache
    lebt = _eltern_wache(os.getppid())
    erst = lebt()
    ende = time.time() + 8
    while time.time() < ende and lebt():
        time.sleep(0.05)
    open(out, "w").write(f"{erst} {lebt()}")

if __name__ == "__main__":
    mp.set_start_method("spawn")
    mp.Process(target=kind, args=(sys.argv[2],)).start()
    time.sleep(2.0)
    os._exit(0)   # Parent stirbt, ohne das Kind zu beenden
"""


class WaisenWacheTest(unittest.TestCase):

    def test_kind_bemerkt_den_tod_des_parents(self):
        tmp = tempfile.mkdtemp(prefix="out59_")
        out = os.path.join(tmp, "ergebnis.txt")
        skript = os.path.join(tmp, "eltern.py")
        with open(skript, "w", encoding="utf-8") as f:
            f.write(_ELTERN)
        env = dict(os.environ, PYTHONPATH=REPO)
        subprocess.run([sys.executable, skript, REPO, out], timeout=30, check=True,
                       cwd=REPO, env=env)
        ende = time.time() + 15
        while time.time() < ende and not os.path.exists(out):
            time.sleep(0.1)
        self.assertTrue(os.path.exists(out), "Kind hat den Tod des Parents nicht bemerkt")
        time.sleep(0.2)
        with open(out, encoding="utf-8") as f:
            erst, zuletzt = f.read().split()
        self.assertEqual(erst, "True", "Wache meldete den lebenden Parent als tot")
        self.assertEqual(zuletzt, "False", "Wache meldet den toten Parent als lebend")

    @unittest.skipUnless(os.name == "nt", "Windows-Pfad")
    def test_windows_nutzt_ein_prozess_handle(self):
        import inspect
        from src.core.dmx import serial_process
        quelle = inspect.getsource(serial_process._eltern_wache)
        self.assertIn("OpenProcess", quelle)
        self.assertIn("WaitForSingleObject", quelle)


if __name__ == "__main__":
    unittest.main()
