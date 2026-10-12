"""XPLAT-36: genannte Dateien bekommen im Segment-Runner 600 s statt 300 s.

**Der Befund.** ``tests/test_viz13_scene_modules_smoke.py`` brauchte allein
269–309 s, im vollen Gate aber nur 114 s — unter Parallellast, also dort, wo
sie langsamer sein müsste. Der Verdacht (ein Cache, den die WebEngine-Segmente
davor wärmen) war ungeprüft.

**Gemessen am 11.10.2026** (Windows x64, 4 Kerne, Energieplan „Ausbalanciert“,
alles ohne Fenster):

==========================================  =========  ====================
im Voll-Gate (30 Läufe)                     137–151 s
allein                                      223–250 s  CPU-Takt 22 % vom Max.
allein + 4 rechnende Prozesse daneben       148–151 s  CPU-Takt 100 %
allein + ein Prozess mit 1-ms-Timer         250 s      keine Wirkung
==========================================  =========  ====================

Die Datei wartet fast nur (Seite laden, Abfragen im 50-ms-Takt, Nachrichten
zwischen Python, Renderer und GPU-Prozess). Auf einem sonst ruhigen Rechner
holt sie die CPU nie aus dem Spartakt; im Gate hält die parallele Spur den
Takt oben. Der Einzellauf ist für solche Dateien also der LANGSAMERE Fall —
und genau der lief gegen ein Limit, das am Voll-Lauf bemessen ist.

**Die Regel.** Sind Dateien genannt, gilt 600 s; der Voll-Lauf bleibt bei
300 s; ein ausdrücklich gesetztes ``-TimeoutSec`` gilt immer. Beide Runner
sagen beim Start, welches Limit gilt.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PS1 = REPO / "tools" / "verify_segmented.ps1"
SH = REPO / "tools" / "verify_segmented.sh"

_IST_WINDOWS = sys.platform == "win32"
_IST_LINUX = sys.platform.startswith("linux")
# Ein Test, der selbst einen Runner startet, erzeugt im Volllauf ein Gate im
# Gate (QA-53). Dieselbe Regel wie in test_xplat27/test_xplat31.
_IM_SEGMENT = bool(os.environ.get("LIGHTOS_IM_SEGMENT"))
_SEGMENT_GRUND = "laeuft selbst als Segment eines Gate-Laufs — kein Gate im Gate (QA-53)"

GRUEN = "def test_ok():\n    assert True\n"


class QuelltextTest(unittest.TestCase):
    """Läuft überall, auch im Gate: die Regel steht in beiden Runnern."""

    def test_windows_vorgabe_bleibt_300(self):
        quelle = PS1.read_text(encoding="utf-8", errors="replace")
        self.assertRegex(quelle, r"\[int\]\$TimeoutSec\s*=\s*300\b",
                         "die Vorgabe fuer den Voll-Lauf ist nicht mehr 300 s")

    def test_windows_genannte_dateien_600_und_ausdruecklicher_wert_gewinnt(self):
        quelle = PS1.read_text(encoding="utf-8", errors="replace")
        self.assertRegex(quelle, r"\$EinzelTimeoutSec\s*=\s*600\b")
        # EINE Bedingung: nicht ausdruecklich gesetzt UND Dateien genannt.
        self.assertRegex(
            quelle,
            r"if\s*\(\s*-not\s+\$PSBoundParameters\.ContainsKey\('TimeoutSec'\)\s+-and\s+"
            r"\$Targets\s+-and\s+\$Targets\.Count\s*\)\s*\{[\s\S]{0,200}?\$TimeoutSec\s*=\s*\$EinzelTimeoutSec",
            "die 600 s haengen nicht (mehr) an 'Dateien genannt UND -TimeoutSec nicht gesetzt'")

    def test_windows_sagt_das_limit_und_warnt_bei_der_gegenprobe(self):
        quelle = PS1.read_text(encoding="utf-8", errors="replace")
        self.assertIn("Zeitlimit je Segment:", quelle)
        self.assertIn("XPLAT-36", quelle)
        self.assertRegex(quelle, r"Gegenprobe darf INSGESAMT laenger dauern",
                         "der Hinweis zur Gegenprobe fehlt: isoliert ist fuer wartende "
                         "Dateien der langsamere Fall")

    def test_linux_dieselbe_regel(self):
        quelle = SH.read_text(encoding="utf-8", errors="replace")
        self.assertRegex(quelle, r"(?m)^SEG_LIMIT=300$")
        self.assertRegex(quelle, r"(?m)^\s+SEG_LIMIT=600$")
        self.assertRegex(quelle, r"(?m)^export SEG_LIMIT$",
                         "run_one laeuft in einer eigenen bash — ohne export saehe es das Limit nicht")
        self.assertRegex(quelle, r'timeout "\$\{SEG_LIMIT:-300\}" "\$PY" -m pytest')
        self.assertNotRegex(quelle, r"timeout 300 \"\$PY\"",
                            "das Limit steht wieder fest im Aufruf")
        self.assertIn("Zeitlimit je Segment:", quelle)

    def test_linux_meldung_nennt_das_geltende_limit(self):
        quelle = SH.read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("(>300s abgebrochen)", quelle,
                         "die ZEIT-Meldung nennt fest 300 s, auch wenn 600 gelten")
        self.assertRegex(quelle, r'\(>%ss abgebrochen\)\\n\' "\$f" "\$\{SEG_LIMIT:-300\}"')


def _umgebung(tmp: Path) -> dict:
    umgebung = dict(os.environ)
    for schluessel in ("LIGHTOS_LOCKFILE", "LIGHTOS_VERIFY_DRYRUN", "LIGHTOS_VERIFY_NOLOCK",
                       "LIGHTOS_VERIFY_SINGLE", "LIGHTOS_IM_SEGMENT"):
        umgebung.pop(schluessel, None)
    umgebung["LIGHTOS_SEG_OUT"] = str(tmp / "out")
    umgebung["LIGHTOS_SHOW_DB"] = str(tmp / "kind_show.db")
    umgebung["QT_QPA_PLATFORM"] = "offscreen"
    return umgebung


@unittest.skipUnless(_IST_WINDOWS, "verify_segmented.ps1 ist das Windows-Gate")
@unittest.skipIf(_IM_SEGMENT, _SEGMENT_GRUND)
class WindowsVerhaltenTest(unittest.TestCase):

    def _lauf(self, *argumente):
        with tempfile.TemporaryDirectory(prefix="lightos_xplat36_") as tmp:
            tmp = Path(tmp)
            probe = tmp / "test_0_probe.py"
            probe.write_text(GRUEN, encoding="utf-8")
            erg = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(PS1), "-j", "1", *argumente, str(probe)],
                cwd=str(REPO), env=_umgebung(tmp), capture_output=True, timeout=600)
            return erg.returncode, (erg.stdout + erg.stderr).decode("utf-8", "replace")

    def test_genannte_datei_bekommt_600(self):
        rc, ausgabe = self._lauf()
        self.assertEqual(0, rc, ausgabe[-800:])
        self.assertRegex(ausgabe, r"Zeitlimit je Segment: 600 s \(Dateien genannt; im Voll-Lauf 300 s\)")

    def test_ausdruecklich_gesetztes_limit_gewinnt(self):
        rc, ausgabe = self._lauf("-TimeoutSec", "123")
        self.assertEqual(0, rc, ausgabe[-800:])
        zeile = re.search(r"Zeitlimit je Segment: .*", ausgabe)
        self.assertIsNotNone(zeile, ausgabe[-800:])
        self.assertEqual(zeile.group(0).strip(), "Zeitlimit je Segment: 123 s")

    def test_ausdruecklich_300_bleibt_300(self):
        """Wer die alte Grenze fuer einen Einzellauf will, bekommt sie."""
        rc, ausgabe = self._lauf("-TimeoutSec", "300")
        self.assertEqual(0, rc, ausgabe[-800:])
        self.assertRegex(ausgabe, r"Zeitlimit je Segment: 300 s\s")
        self.assertNotIn("Dateien genannt", ausgabe)


@unittest.skipUnless(_IST_LINUX, "verify_segmented.sh ist das Linux-Gate")
@unittest.skipIf(_IM_SEGMENT, _SEGMENT_GRUND)
class LinuxVerhaltenTest(unittest.TestCase):

    def test_genannte_datei_bekommt_600(self):
        with tempfile.TemporaryDirectory(prefix="lightos_xplat36_") as tmp:
            tmp = Path(tmp)
            probe = tmp / "test_0_probe.py"
            probe.write_text(GRUEN, encoding="utf-8")
            erg = subprocess.run(["bash", str(SH), str(probe)], cwd=str(REPO),
                                 env=_umgebung(tmp), capture_output=True, timeout=600)
            ausgabe = (erg.stdout + erg.stderr).decode("utf-8", "replace")
        self.assertEqual(0, erg.returncode, ausgabe[-800:])
        self.assertIn("Zeitlimit je Segment: 600 s (Dateien genannt; im Voll-Lauf 300 s)", ausgabe)


if __name__ == "__main__":
    unittest.main()
