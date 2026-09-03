"""XPLAT-29 (a): das Aufraeumen darf den Gate-Lauf nicht beenden.

**Der Vorfall (01.09.2026).** Ein Gate-Start endete sofort — ohne ein einziges
Segment — mit::

    Remove-Item : Das Element ...tests_test_viz50a_panel_koerper_scene.py.log
    kann nicht entfernt werden ... da sie von einem anderen Prozess verwendet wird

Am Leben waren zwei ``python`` und ein ``QtWebEngineProcess`` aus dem VORIGEN
Lauf, gestartet lange vor dem Ende ihres Gates: Windows reisst Prozessbaeume
nicht mit, Kinder ueberleben ihren Elternprozess (dieselbe Wurzel wie XPLAT-24).

★ **Warum das die teuerste Variante ist.** Ein Lauf, der VOR dem ersten Segment
endet, sieht aus wie ein rotes Gate und hat dabei **nichts gemessen**. Wer die
Zeile liest, sucht den Fehler im eigenen Diff. Es ist dieselbe Klasse wie
XPLAT-27 (haengendes Segment beendet den Lauf) und XPLAT-31 (kein gruenes
Segment ergibt Exit 0): *der Runner soll mit dem Schaden umgehen, statt an ihm
zu sterben.*

**Was hier NICHT passiert:** die Waisen werden benannt, nicht beendet. Sie
wirklich zu toeten ist XPLAT-29(b) und liegt bei Robin — es hiesse, dass ein
Absturz des Hauptprozesses den DMX-Worker mitreisst, also im Zweifel Licht aus
statt eingefrorenem Standbild. Ausserdem haelt die laufende App des Menschen
selbst Chromium-Kinder (COORDINATION.md: „Die laufende App gehoert dem
Menschen").
"""
from __future__ import annotations

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
_GRUND = ("verify_segmented.ps1 ist das Windows-Gate; auf Linux gibt es den Fall "
          "nicht — dort raeumt der Runner ein Verzeichnis, das kein fremder "
          "Prozess exklusiv haelt")

#: Wie XPLAT-27/31: dieser Test startet selbst einen Segment-Runner. Im
#: Volllauf waere das ein Gate IM Gate (QA-53), und der innere Lauf scheitert
#: dort reproduzierbar. Der Runner setzt das Merkmal fuer seine Kinder.
_IM_SEGMENT = bool(os.environ.get("LIGHTOS_IM_SEGMENT"))
_SEGMENT_GRUND = (
    "startet selbst einen Segment-Runner — im Volllauf waere das ein Gate IM "
    "Gate (QA-53). Gezielter Nachweis: "
    ".\\tools\\verify_loop.ps1 tests\\test_xplat29_aufraeumen_stirbt_nicht.py")

GRUEN = "def test_ok():\n    assert True\n"

#: Haelt eine Datei exklusiv (FileShare::None) und wartet auf einen Tastendruck,
#: der nie kommt — beendet wird der Prozess vom Test.
_HALTER = (
    "$h = [System.IO.File]::Open('{pfad}', 'Open', 'Read', 'None'); "
    "Write-Host 'HALTE'; "
    "while ($true) {{ Start-Sleep -Milliseconds 200 }}")


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
@unittest.skipIf(_IM_SEGMENT, _SEGMENT_GRUND)
class AufraeumenStirbtNichtTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lightos_xplat29_")
        self.tmp = Path(self._tmp.name)
        self.probe = self.tmp / "test_probe_gruen.py"
        self.probe.write_text(GRUEN, encoding="utf-8")
        self.out = self.tmp / "out"
        self.out.mkdir()
        self.halter = None

    def tearDown(self):
        if self.halter and self.halter.poll() is None:
            self.halter.kill()
            self.halter.wait(timeout=30)
        self._tmp.cleanup()

    def _halte_datei(self, pfad: Path):
        """Eine Datei im Ausgabeverzeichnis exklusiv halten — wie eine Waise."""
        pfad.write_text("aus dem vorigen Lauf\n", encoding="utf-8")
        self.halter = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", _HALTER.format(pfad=str(pfad))],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        # Warten, bis die Datei wirklich gehalten wird: sonst raeumt der Runner
        # sie klaglos weg und der Test prueft den falschen Zweig.
        ende = time.monotonic() + 60
        while time.monotonic() < ende:
            if self.halter.poll() is not None:
                self.fail("der Halter ist gestorben, bevor er die Datei hatte")
            try:
                with open(pfad, "a", encoding="utf-8"):
                    pass
            except OSError:
                return                      # nicht mehr oeffenbar = gehalten
            time.sleep(0.05)
        self.fail("die Datei wurde nie exklusiv gehalten")

    def _lauf(self):
        umgebung = dict(os.environ)
        umgebung["LIGHTOS_SEG_OUT"] = str(self.out)
        umgebung["LIGHTOS_SHOW_DB"] = str(self.tmp / "kind_show.db")
        umgebung["QT_QPA_PLATFORM"] = "offscreen"
        umgebung.pop("LIGHTOS_IM_SEGMENT", None)
        erg = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(RUNNER), "-j", "1", str(self.probe)],
            cwd=str(REPO), env=umgebung, capture_output=True, timeout=900)
        return erg.returncode, (erg.stdout + erg.stderr).decode("utf-8", "replace")

    def test_eine_gehaltene_datei_beendet_den_lauf_nicht(self):
        """★★ Der eigentliche Nachweis — vorher endete hier alles vor Segment 1."""
        self._halte_datei(self.out / "alt.log")
        rc, ausgabe = self._lauf()
        self.assertEqual(0, rc,
                         "der Lauf ist am Aufraeumen gestorben — genau das ist "
                         f"XPLAT-29(a):\n{ausgabe[-1200:]}")
        self.assertRegex(ausgabe, r"1/1 Segmente gruen",
                         "der Lauf hat kein Segment gefahren — er sieht aus wie "
                         f"ein Ergebnis und ist keins:\n{ausgabe[-1200:]}")
        self.assertIn("XPLAT-29", ausgabe,
                      "der Lauf ist ausgewichen, ohne es zu sagen — dann sucht "
                      f"niemand die Waisen:\n{ausgabe[-1200:]}")
        self.assertIn("Ausgewichen auf", ausgabe, ausgabe[-1200:])

    def test_der_haltende_prozess_wird_NICHT_beendet(self):
        """★ Die Abgrenzung zu XPLAT-29(b), und sie ist keine Formsache.

        Waisen zu toeten liegt bei Robin, weil derselbe Griff im Absturzfall den
        DMX-Worker mitreisst. Und die laufende App des Menschen haelt ebenfalls
        Chromium-Kinder — ein Runner, der beim Aufraeumen zuschlaegt, nimmt ihm
        mitten in der Show das Licht.
        """
        self._halte_datei(self.out / "alt.log")
        halter = self.halter
        assert halter is not None            # _halte_datei setzt ihn oder failt
        ausgabe = self._lauf()[1]
        self.assertIsNone(
            halter.poll(),
            "der haltende Prozess wurde beendet — das ist XPLAT-29(b) und liegt "
            "bei Robin, nicht hier")
        self.assertIn("NICHTS beendet", ausgabe, ausgabe[-1200:])

    def test_ohne_hindernis_wird_normal_geraeumt(self):
        """★ Positivkontrolle: aus dem Ausweichen darf kein Dauerzustand werden.

        Ohne sie koennte der Runner IMMER ausweichen — alle Tests oben blieben
        gruen, und das Ausgabeverzeichnis fuellte sich mit Ordnern, waehrend die
        alten Logs nie verschwaenden.
        """
        alt = self.out / "alt.log"
        alt.write_text("aus dem vorigen Lauf\n", encoding="utf-8")
        rc, ausgabe = self._lauf()
        self.assertEqual(0, rc, ausgabe[-1200:])
        self.assertNotIn("Ausgewichen auf", ausgabe,
                         "der Runner weicht aus, obwohl nichts im Weg war:\n"
                         + ausgabe[-1200:])
        self.assertFalse(alt.exists(),
                         "das Logfile des vorigen Laufs steht noch da — dann "
                         "mischen sich alte und neue Ergebnisse")
        self.assertRegex(ausgabe, r"1/1 Segmente gruen", ausgabe[-1200:])


if __name__ == "__main__":
    unittest.main()
