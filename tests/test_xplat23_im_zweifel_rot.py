"""XPLAT-23/QA-53: eine unvollstaendige Bilanz darf nicht gruen melden.

**Die Luecke.** `verify_segmented.sh` faengt seit QA-53 den Fall ab, dass die
Ergebnisliste weniger Zeilen hat, als Dateien gefahren wurden — dann ist die
Zahl in der Bilanz nicht bloss ungenau, sondern irrefuehrend: ein Teillauf sieht
aus wie ein Volllauf. Auf der `.ps1`-Seite fehlte diese Regel.

★ **Der Fall ist auf Windows real und nicht theoretisch.** Beide Runner
benutzen dasselbe Ausgabeverzeichnis, egal ob Volllauf oder gezielter
Einzellauf (`LIGHTOS_SEG_OUT`, sonst `.pytest_segments`). Wer waehrend eines
Volllaufs einen Einzeltest startet, raeumt dem Volllauf die Ergebniszeilen weg —
der zaehlt danach nur noch seinen Rest. Die Voll-Suiten-Sperre aus Scheibe 1
faengt das nicht: gezielte Laeufe sind bewusst ungesperrt.

★★ **Die gefaehrlichere Haelfte ist nicht die falsche Zahl — die sieht man —,
sondern das falsche GRUEN darunter.** Wer nicht weiss, ob alles gelaufen ist,
hat kein bestandenes Gate, sondern ein kaputtes Messgeraet.

**Zweite Haelfte dieses Tests:** die Ergebniszeile selbst darf den Lauf nicht
mitreissen. Gemessen: `Add-Content` auf eine exklusiv gehaltene Datei wirft eine
`IOException`, und unter `$ErrorActionPreference = "Stop"` beendete die bis
hierhin den ganzen Lauf — mitten drin, nach getaner Arbeit, die damit verloren
war. Dieselbe Klasse wie XPLAT-27 und XPLAT-29.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tools" / "verify_segmented.ps1"

_IST_WINDOWS = sys.platform == "win32"
_GRUND = ("verify_segmented.ps1 ist das Windows-Gate; auf Linux deckt "
          "verify_segmented.sh denselben Fall seit QA-53 ab")

_IM_SEGMENT = bool(os.environ.get("LIGHTOS_IM_SEGMENT"))
_SEGMENT_GRUND = (
    "startet selbst einen Segment-Runner — im Volllauf waere das ein Gate IM "
    "Gate (QA-53). Gezielter Nachweis: "
    ".\\tools\\verify_loop.ps1 tests\\test_xplat23_im_zweifel_rot.py")

PROBE = "def test_ok():\n    assert True\n"


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
@unittest.skipIf(_IM_SEGMENT, _SEGMENT_GRUND)
class ImZweifelRotTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lightos_qa53_")
        self.tmp = Path(self._tmp.name)
        self.out = self.tmp / "out"
        self.dateien = []
        for i in (1, 2):
            p = self.tmp / f"test_p{i}.py"
            p.write_text(PROBE, encoding="utf-8")
            self.dateien.append(str(p))
        self.halter = None

    def tearDown(self):
        if self.halter is not None and self.halter.poll() is None:
            self.halter.kill()
            self.halter.wait(timeout=30)
        self._tmp.cleanup()

    def _greife_results_tsv(self):
        """Sobald ``results.tsv`` entsteht, exklusiv halten — wie ein fremder Lauf.

        Vorher geht es nicht: der Runner legt die Datei erst beim ersten
        Ergebnis an, und ein vorher angelegtes (und gehaltenes) Exemplar liesse
        ihn nach XPLAT-29(a) auf ein frisches Unterverzeichnis ausweichen — dann
        waere die Liste wieder vollstaendig und der Test pruefte nichts.
        """
        res = self.out / "results.tsv"

        def warten():
            ende = time.monotonic() + 180
            while time.monotonic() < ende:
                if res.exists():
                    self.halter = subprocess.Popen(
                        ["powershell", "-NoProfile", "-Command",
                         f"$h=[System.IO.File]::Open('{res}','Open','ReadWrite','None'); "
                         "while($true){Start-Sleep -Milliseconds 200}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                time.sleep(0.02)

        threading.Thread(target=warten, daemon=True).start()

    def _lauf(self, timeout=600):
        umgebung = dict(os.environ)
        umgebung["LIGHTOS_SEG_OUT"] = str(self.out)
        umgebung["LIGHTOS_SHOW_DB"] = str(self.tmp / "kind_show.db")
        umgebung["QT_QPA_PLATFORM"] = "offscreen"
        umgebung.pop("LIGHTOS_IM_SEGMENT", None)
        erg = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(RUNNER), "-j", "1", *self.dateien],
            cwd=str(REPO), env=umgebung, capture_output=True, timeout=timeout)
        return erg.returncode, (erg.stdout + erg.stderr).decode("utf-8", "replace")

    def test_eine_unvollstaendige_bilanz_ergibt_KEIN_gruen(self):
        """★★ Der eigentliche Nachweis — beide Segmente gruen, der Lauf trotzdem rot."""
        self._greife_results_tsv()
        rc, ausgabe = self._lauf()
        self.assertIsNotNone(
            self.halter,
            "die Ergebnisliste wurde nie belegt — dann prueft dieser Test den "
            "gesunden Fall und ist immer gruen")
        self.assertRegex(ausgabe, r"2/2 Segmente gruen",
                         "die Segmente selbst waren nicht gruen — dann faerbt "
                         f"schon ihr Ergebnis rot und nicht die Regel:\n{ausgabe[-900:]}")
        self.assertIn("UNVOLLSTAENDIG", ausgabe,
                      "die Unvollstaendigkeit wird nicht gemeldet:\n" + ausgabe[-900:])
        self.assertIn("KEIN Gruen (QA-53)", ausgabe, ausgabe[-900:])
        self.assertNotEqual(
            0, rc,
            "zwei gruene Segmente und eine leere Ergebnisliste - und das Gate "
            f"meldet Erfolg. Das ist das falsche GRUEN:\n{ausgabe[-900:]}")

    def test_die_ergebniszeile_reisst_den_lauf_nicht_mit(self):
        """★ Zweite Haelfte: der Runner stirbt nicht am Schreibfehler.

        Vor der Haertung beendete die IOException aus ``Add-Content`` unter
        ``$ErrorActionPreference = "Stop"`` den ganzen Lauf — mitten drin. Dass
        BEIDE Segmente unten noch durchlaufen, ist der Beleg.
        """
        self._greife_results_tsv()
        _rc, ausgabe = self._lauf()
        self.assertIsNotNone(self.halter, "die Ergebnisliste wurde nie belegt")
        self.assertIn("Ergebniszeile nicht schreibbar", ausgabe,
                      "der Schreibfehler wird verschwiegen:\n" + ausgabe[-900:])
        for datei in self.dateien:
            self.assertIn(Path(datei).name, ausgabe,
                          f"{Path(datei).name} lief nicht mehr — der Lauf ist am "
                          f"Schreibfehler gestorben:\n{ausgabe[-900:]}")

    def test_ein_gesunder_lauf_bleibt_gruen(self):
        """★ Positivkontrolle: aus der Regel darf kein Dauer-Rot werden.

        Ohne sie koennte die Pruefung immer anschlagen und alle Tests oben
        blieben gruen — aus dem Schutz gegen falsches Gruen waere dann ein Gate
        geworden, das nie mehr besteht.
        """
        rc, ausgabe = self._lauf()
        self.assertEqual(0, rc, ausgabe[-900:])
        self.assertNotIn("UNVOLLSTAENDIG", ausgabe, ausgabe[-900:])
        self.assertNotIn("KEIN Gruen", ausgabe, ausgabe[-900:])
        self.assertRegex(ausgabe, r"2/2 Segmente gruen", ausgabe[-900:])


if __name__ == "__main__":
    unittest.main()
