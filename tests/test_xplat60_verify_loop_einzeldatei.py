"""XPLAT-60: ``tools/verify_loop.ps1`` mit GENAU EINER Testdatei.

**Der Fehler.** Ohne den Lock-Runner ``../run_tests.ps1`` (er liegt ausserhalb
des Repos und fehlt auf jedem frischen Windows-Rechner) faehrt das Skript eine
gezielte Datei direkt mit pytest::

    $target = if ($TestArgs) { $TestArgs } else { @("tests/") }
    & $py -m pytest @target ...

Die Zuweisung eines ``if``-Ausdrucks entrollt in PowerShell ein Array mit nur
einem Element zu seinem Element — ``$target`` ist dann eine Zeichenkette, und
``@target`` reicht davon nur das erste Zeichen weiter. Gemessen am 01.11.2026
unter Windows 11 x64: ``.\\tools\\verify_loop.ps1 tests\\test_x.py`` endete mit
``ERROR: file or directory not found: t`` und Exit 1; mit zwei Dateien lief es.
Genau so stand der Aufruf aber im Auftrag (``verify_loop.ps1 tests\\test_….py``).

**Wie geprueft wird.** Am Verhalten, nicht am Text: der echte Runner bekommt
eine winzige Testdatei in einem eigenen Temp-Ordner (absoluter Pfad, beginnt
also mit dem Laufwerksbuchstaben — ohne Fix kaeme bei pytest nur ``C`` an).
Ist ``../run_tests.ps1`` vorhanden, nimmt das Skript den anderen Zweig; dann
gibt es hier nichts zu pruefen und der Test wird uebersprungen.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tools" / "verify_loop.ps1"
LOCK_RUNNER = REPO.parent / "run_tests.ps1"

_IST_WINDOWS = sys.platform == "win32"


def _lauf(*argumente, timeout=300):
    umgebung = dict(os.environ)
    # Schalter des aeusseren Gate-Laufs nicht erben (siehe test_xplat23_windows_sperre).
    for schluessel in ("LIGHTOS_VERIFY_DRYRUN", "LIGHTOS_VERIFY_DRYRUN_HOLD_MS",
                       "LIGHTOS_VERIFY_NOLOCK", "LIGHTOS_LOCKFILE"):
        umgebung.pop(schluessel, None)
    erg = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(RUNNER), *argumente],
        cwd=str(REPO), env=umgebung, capture_output=True, timeout=timeout)
    return erg.returncode, (erg.stdout + erg.stderr).decode("utf-8", "replace")


@unittest.skipUnless(_IST_WINDOWS, "verify_loop.ps1 ist das Windows-Gate")
@unittest.skipIf(LOCK_RUNNER.exists(),
                 "../run_tests.ps1 vorhanden - der Einzeldatei-Weg ohne Lock-Runner "
                 "wird auf diesem Rechner nicht genommen")
class EinzeldateiOhneLockRunnerTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="xplat60_")
        self.ordner = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _datei(self, name, inhalt="def test_ok():\n    assert True\n"):
        p = self.ordner / name
        p.write_text(inhalt, encoding="utf-8")
        return p

    def test_genau_eine_datei_wird_ganz_an_pytest_gereicht(self):
        datei = self._datei("test_xplat60_eine.py")
        rc, aus = _lauf(str(datei))
        self.assertNotIn("file or directory not found", aus, aus[-1500:])
        self.assertIn("1 passed", aus, aus[-1500:])
        self.assertEqual(rc, 0, aus[-1500:])

    def test_eine_rote_datei_bleibt_rot(self):
        """Gegenprobe: der Fix darf aus „nichts gefunden" kein „gruen" machen."""
        datei = self._datei("test_xplat60_rot.py", "def test_rot():\n    assert False\n")
        rc, aus = _lauf(str(datei))
        self.assertIn("1 failed", aus, aus[-1500:])
        self.assertNotEqual(rc, 0, aus[-1500:])

    def test_zwei_dateien_wie_bisher(self):
        a = self._datei("test_xplat60_a.py")
        b = self._datei("test_xplat60_b.py")
        rc, aus = _lauf(str(a), str(b))
        self.assertIn("2 passed", aus, aus[-1500:])
        self.assertEqual(rc, 0, aus[-1500:])


if __name__ == "__main__":
    unittest.main()
