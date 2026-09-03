"""XPLAT-23: die rechnerweite WebEngine-Sperre des Windows-Gates.

**Der Zustand vorher.** `verify_segmented.ps1` faehrt WebEngine-Segmente seit
XPLAT-17 in einer seriellen Spur — aber nur INNERHALB eines Laufs. Ungeschuetzt
war der Fall ZWISCHEN Prozessen: ein gezielter Einzellauf auf eine
WebEngine-Datei neben einem Volllauf, oder zwei Sitzungen auf demselben Rechner
(seit 2026-08-06 der Normalfall, COORDINATION.md). Dann leben zwei WebGL-
Kontexte gleichzeitig — genau die Ursache, gegen die PROC-02c auf Linux die
schmale Sperre gebaut hat. Auf der `.sh`-Seite gibt es sie seit August, auf der
`.ps1`-Seite gab es sie gar nicht.

**Frischer Beleg** (Sitzung B, Nacht 02./03.09.2026): ein eigener Gate-Lauf
meldete „1 WebEngine-Segment startete, obwohl noch Chromium-Kindprozesse liefen
(3-s-Deckel erreicht)".

★ **Die wichtigste Zusicherung hier ist nicht, dass gesperrt wird, sondern dass
die Sperre das Gate NIE anhaelt.** Eine Sperre, die haengt, waere schlimmer als
keine: sie verwandelt eine knappe Ressource in einen Stillstand. Deshalb steht
die Wartezeit unter einem Deckel, und jeder Ausgang laeuft weiter.
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
GETEILT = REPO / "tools" / "_gate_webengine.ps1"

_IST_WINDOWS = sys.platform == "win32"
_GRUND = ("verify_segmented.ps1 ist das Windows-Gate; auf Linux macht das "
          "tools/_gate_webengine.sh und wird von test_gate_webengine_lane.py geprueft")

#: Wie XPLAT-27/29/31: dieser Test startet selbst einen Segment-Runner. Im
#: Volllauf waere das ein Gate IM Gate (QA-53).
_IM_SEGMENT = bool(os.environ.get("LIGHTOS_IM_SEGMENT"))
_SEGMENT_GRUND = (
    "startet selbst einen Segment-Runner — im Volllauf waere das ein Gate IM "
    "Gate (QA-53). Gezielter Nachweis: "
    ".\\tools\\verify_loop.ps1 tests\\test_xplat23_webengine_sperre.py")

#: Marker, an dem der Runner die serielle Spur erkennt. Als Kommentar genuegt er
#: — der Test braucht keine echte WebEngine, nur die Einordnung.
WEB_PROBE = ("# QWebEngineView (Merkmal fuer die WebEngine-Spur)\n"
             "def test_ok():\n    assert True\n")
SCHNELL_PROBE = "def test_ok():\n    assert True\n"


class GeteilteDateiTest(unittest.TestCase):
    """Die Sperre liegt in einer EIGENEN Datei, nicht als Kopie im Runner.

    Laeuft auf jeder Plattform: es ist dieselbe Zusicherung, die
    `test_gate_runner_parity` fuer die Runner trifft. XPLAT-11 war die Drift
    zweier Gate-Runner, die auseinandergelaufen sind — eine kopierte Sperre
    waere die naechste.
    """

    def test_die_geteilte_datei_existiert_und_wird_eingebunden(self):
        self.assertTrue(GETEILT.is_file(),
                        f"{GETEILT.name} fehlt — dann steht die Sperre wieder "
                        "als Kopie im Runner")
        quelle = RUNNER.read_text(encoding="utf-8", errors="replace")
        self.assertIn("_gate_webengine.ps1", quelle,
                      "verify_segmented.ps1 bindet die geteilte Datei nicht ein")
        for name in ("Enter-WebEngineSperre", "Exit-WebEngineSperre"):
            self.assertIn(name, quelle, f"{name} wird nicht aufgerufen")


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
@unittest.skipIf(_IM_SEGMENT, _SEGMENT_GRUND)
class WebEngineSperreTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lightos_xplat23web_")
        self.tmp = Path(self._tmp.name)
        self.sperre = self.tmp / "webengine.lock"
        self.halter = None

    def tearDown(self):
        if self.halter is not None and self.halter.poll() is None:
            self.halter.kill()
            self.halter.wait(timeout=30)
        self._tmp.cleanup()

    def _halte_sperre(self):
        """Die Sperrdatei exklusiv halten — wie ein zweiter Gate-Lauf.

        ⚠️ Bewusst ueber einen PowerShell-Prozess mit ``FileShare::None`` und
        NICHT ueber ``msvcrt.locking``: das sperrt einen Byte-Bereich und
        verhindert Lesen/Schreiben, nicht das OEFFNEN. Der Runner oeffnet aber
        nur — ein Byte-Bereichs-Halter kaeme ihm gar nicht in die Quere, und
        der Test bewiese nichts. Gehalten wird also mit derselben Primitive,
        gegen die die Sperre wirkt.
        """
        self.sperre.write_text("x", encoding="utf-8")
        befehl = (f"$h = [System.IO.File]::Open('{self.sperre}', 'Open', "
                  "'ReadWrite', 'None'); Write-Host 'HALTE'; "
                  "while ($true) { Start-Sleep -Milliseconds 200 }")
        self.halter = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", befehl],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        # Warten, bis wirklich gehalten wird: sonst prueft der Test den
        # ungesperrten Fall und ist immer gruen.
        ende = time.monotonic() + 60
        while time.monotonic() < ende:
            if self.halter.poll() is not None:
                self.fail("der Halter ist gestorben, bevor er die Sperre hatte")
            try:
                with open(self.sperre, "r+b"):
                    pass
            except OSError:
                return                      # nicht mehr oeffenbar = gehalten
            time.sleep(0.05)
        self.fail("die Sperrdatei wurde nie exklusiv gehalten")

    def _lauf(self, inhalt=WEB_PROBE, warte="5", extra=None, timeout=300):
        probe = self.tmp / "test_web_probe.py"
        probe.write_text(inhalt, encoding="utf-8")
        umgebung = dict(os.environ)
        umgebung["LIGHTOS_SEG_OUT"] = str(self.tmp / "out")
        umgebung["LIGHTOS_SHOW_DB"] = str(self.tmp / "kind_show.db")
        umgebung["LIGHTOS_WEBENGINE_LOCKFILE"] = str(self.sperre)
        umgebung["LIGHTOS_WEBENGINE_SPERRE_WARTE"] = warte
        umgebung["QT_QPA_PLATFORM"] = "offscreen"
        for weg in ("LIGHTOS_IM_SEGMENT", "LIGHTOS_WEBENGINE_LOCK_HELD",
                    "LIGHTOS_WEBENGINE_NOLOCK"):
            umgebung.pop(weg, None)
        umgebung.update(extra or {})
        beginn = time.monotonic()
        erg = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(RUNNER), "-j", "1", str(probe)],
            cwd=str(REPO), env=umgebung, capture_output=True, timeout=timeout)
        dauer = time.monotonic() - beginn
        return erg.returncode, (erg.stdout + erg.stderr).decode("utf-8", "replace"), dauer

    # ── Spur-Einordnung ─────────────────────────────────────────────────────
    def test_eine_absolut_angegebene_webengine_datei_landet_in_der_seriellen_spur(self):
        """Nebenbefund aus dem Bau dieser Sperre — und Vorbedingung fuer alles
        Weitere hier.

        Die Einordnung baute den Pfad ueber ``Join-Path $repo``; bei einem
        ABSOLUTEN Pfad ergibt das Unsinn, ``Test-Path`` schlaegt fehl, und die
        Datei landete still in der SCHNELLEN Spur — also ausgerechnet ohne die
        Serialisierung, fuer die es die Spur gibt.
        """
        _rc, ausgabe, _d = self._lauf()
        self.assertRegex(ausgabe, r"Spuren: 0 parallel, 1 WebEngine seriell",
                         "die WebEngine-Datei wurde nicht als solche erkannt:\n"
                         + ausgabe[-800:])

    def test_eine_gewoehnliche_datei_bleibt_in_der_schnellen_spur(self):
        """Gegenprobe: aus „alles seriell" waere eine Bremse geworden."""
        _rc, ausgabe, _d = self._lauf(inhalt=SCHNELL_PROBE)
        self.assertRegex(ausgabe, r"Spuren: 1 parallel, 0 WebEngine seriell",
                         ausgabe[-800:])

    # ── Die Sperre selbst ───────────────────────────────────────────────────
    def test_ein_webengine_segment_wartet_auf_eine_fremde_sperre(self):
        """★ Der eigentliche Nachweis."""
        self._halte_sperre()
        rc, ausgabe, dauer = self._lauf(warte="5")
        self.assertIn("wartet auf die rechnerweite Sperre", ausgabe,
                      "die belegte Sperre wurde nicht bemerkt:\n" + ausgabe[-800:])
        self.assertGreater(dauer, 4.0,
                           f"nach {dauer:.1f}s durch — es wurde nicht gewartet")
        self.assertEqual(0, rc, ausgabe[-800:])

    def test_die_sperre_haelt_das_gate_NIE_an(self):
        """★★ Die wichtigere Haelfte.

        Eine Sperre, die haengt, verwandelt eine knappe Ressource in einen
        Stillstand. Nach der Wartezeit laeuft der Lauf weiter — und sagt, dass
        er es tut.
        """
        self._halte_sperre()
        rc, ausgabe, dauer = self._lauf(warte="3")
        self.assertEqual(0, rc,
                         "der Lauf ist an der Sperre gescheitert statt "
                         f"weiterzumachen:\n{ausgabe[-800:]}")
        self.assertIn("weiter ohne", ausgabe, ausgabe[-800:])
        self.assertRegex(ausgabe, r"1/1 Segmente gruen",
                         "das Segment lief gar nicht:\n" + ausgabe[-800:])
        self.assertLess(dauer, 120, f"der Lauf hing {dauer:.0f}s")

    def test_wiedereintritt_wartet_NICHT_auf_sich_selbst(self):
        """★★ Ohne diesen Schutz verklemmt sich das Gate an sich selbst.

        Ein Runner, der INNERHALB eines Segments laeuft, das die Sperre bereits
        haelt, darf sie nicht noch einmal nehmen — sonst wartet er auf den
        eigenen Elternlauf, bis die Wartezeit ablaeuft. Genau dieser Fall ist
        real: die Gate-Tests zaehlen selbst als WebEngine-Segment und starten
        den Segment-Runner erneut.
        """
        self._halte_sperre()
        rc, ausgabe, dauer = self._lauf(
            warte="60", extra={"LIGHTOS_WEBENGINE_LOCK_HELD": "1"})
        self.assertNotIn("wartet auf die rechnerweite Sperre", ausgabe,
                         "der Wiedereintritts-Schutz greift nicht — der Lauf "
                         f"wartet auf sich selbst:\n{ausgabe[-800:]}")
        self.assertLess(dauer, 60,
                        f"der Lauf brauchte {dauer:.0f}s — er hat trotzdem gewartet")
        self.assertEqual(0, rc, ausgabe[-800:])

    def test_ein_unbrauchbarer_sperrpfad_bremst_nicht(self):
        """Anders als die Voll-Suiten-Sperre bricht diese NICHT ab.

        Der Unterschied ist beabsichtigt und steht im Kopf der geteilten Datei:
        jene schuetzt die Gueltigkeit des Ergebnisses, diese hier nur eine
        knappe Ressource.
        """
        self.sperre = self.tmp / "gibt_es_nicht" / "webengine.lock"
        rc, ausgabe, dauer = self._lauf(warte="60")
        self.assertEqual(0, rc, ausgabe[-800:])
        self.assertIn("nicht benutzbar", ausgabe, ausgabe[-800:])
        self.assertLess(dauer, 60, f"der Lauf wartete {dauer:.0f}s auf einen "
                                   "Pfad, den es nicht gibt")

    def test_nach_dem_lauf_ist_die_sperre_wieder_frei(self):
        """★ Sonst haette der naechste Lauf sie fuer immer gegen sich.

        Geprueft am echten Mechanismus statt an einem nachgebauten Halter: der
        ZWEITE Lauf darf nicht warten. Waere die Sperre nach dem ersten Lauf
        noch gehalten, stuende hier „wartet auf die rechnerweite Sperre".
        """
        rc, ausgabe, _d = self._lauf(warte="5")
        self.assertEqual(0, rc, ausgabe[-800:])
        self.assertTrue(self.sperre.exists(),
                        "die Sperrdatei wurde gar nicht angelegt — dann hat der "
                        f"Lauf sie nie genommen:\n{ausgabe[-800:]}")
        rc2, ausgabe2, dauer2 = self._lauf(warte="30")
        self.assertEqual(0, rc2, ausgabe2[-800:])
        self.assertNotIn("wartet auf die rechnerweite Sperre", ausgabe2,
                         "der erste Lauf hat die Sperre nicht freigegeben:\n"
                         + ausgabe2[-800:])
        self.assertLess(dauer2, 30, f"der zweite Lauf brauchte {dauer2:.0f}s")


if __name__ == "__main__":
    unittest.main()
