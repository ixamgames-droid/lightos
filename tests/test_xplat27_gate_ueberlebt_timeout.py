"""XPLAT-27: ein haengendes Segment darf nicht den ganzen Gate-Lauf beenden.

**Der Vorfall (01.09.2026).** Ein Volllauf von ``tools/verify_segmented.ps1``
auf ``main`` endete nach **404 von 646 Segmenten** mit Exit 1 und dieser Zeile:

    taskkill.exe : FEHLER: Der Prozess mit PID 4656 (untergeordnetem Prozess
    von PID 12028) konnte nicht beendet werden.

Das sah aus wie ein rotes Gate und war ein **abgebrochenes**. Der Unterschied
ist erheblich: 242 Testdateien waren gar nicht gefahren, und die Bilanz darunter
zaehlt nur, was sie gesehen hat. Wer die Zahl liest, haelt einen Teillauf fuer
einen Volllauf — dieselbe Klasse Fehler wie QA-53, nur an anderer Stelle.

**Die Ursache** ist eine PowerShell-Eigenheit, die im Haus schon einmal Geld
gekostet hat. ``verify_segmented.ps1`` setzt oben ``$ErrorActionPreference =
"Stop"``. Schreibt ein NATIVES Programm auf stderr, macht PowerShell 5.1 daraus
einen ``NativeCommandError`` — und unter ``Stop`` ist der **terminierend**.
``2>$null`` unterdrueckt nur die Anzeige, nicht den ErrorRecord.

Genau das passiert beim Timeout-Abbau: ``taskkill /T /F`` meldet auf stderr,
wenn ein Kind sich nicht beenden laesst, und bei einem haengenden
Qt-/WebEngine-Segment ist das der Normalfall. Der Abbau der einen Datei riss
damit den ganzen Lauf mit.

``tools/verify_loop.ps1`` hat dieselbe Falle beim ``& powershell``-Aufruf des
Lock-Runners laengst benannt und geloest (lokal ``Continue``); hier fehlte sie.

★ **Warum dieser Test zweigeteilt ist.** Ein *scheiterndes* ``taskkill`` laesst
sich nicht zuverlaessig herstellen — ob ein Kind sich beenden laesst, haengt am
Zufall des Augenblicks. Der Verhaltenstest unten weist deshalb die eigentliche
Zusicherung nach (der Lauf ueberlebt einen Timeout und faehrt die restlichen
Dateien), und der statische Test nagelt die Bedingung fest, unter der das auch
dann gilt, wenn ``taskkill`` sich beschwert. Nur zusammen decken sie den
Vorfall ab.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tools" / "verify_segmented.ps1"

_PLAT = sys.platform
_IST_WINDOWS = _PLAT == "win32"
_GRUND = ("verify_segmented.ps1 ist das Windows-Gate; auf Linux macht das "
          "verify_segmented.sh und hat diese PowerShell-Eigenheit nicht")

SCHNELL = "def test_schnell():\n    assert True\n"
#: Die Schlafdauer wird zur Laufzeit eingesetzt (s. ``setUpClass``) — eine
#: feste Zahl waere unter Parallellast entweder zu kurz (der Haenger reisst das
#: Zeitlimit nicht) oder unnoetig teuer.
HAENGT = "import time\n\n\ndef test_haengt():\n    time.sleep({sek})\n"


class TaskkillDarfDenLaufNichtKippenTest(unittest.TestCase):
    """Statisch: die Bedingung, unter der der Abbau gutartig bleibt."""

    def test_taskkill_steht_in_einem_continue_block(self):
        """``$ErrorActionPreference`` muss um den ``taskkill``-Aufruf herum auf
        ``Continue`` stehen.

        Geprueft wird der Textabschnitt zwischen dem Setzen von ``Continue`` und
        dem naechsten ``finally`` — reicht der nicht ueber den ``taskkill``, ist
        der Aufruf ungeschuetzt und der Vorfall vom 01.09. kann sich wiederholen.
        """
        quelle = RUNNER.read_text(encoding="utf-8", errors="replace")
        self.assertIn("taskkill", quelle, "der Runner beendet gar nichts mehr?")
        geschuetzt = False
        for block in re.finditer(
                r'\$ErrorActionPreference\s*=\s*"Continue"(.*?)finally',
                quelle, re.S):
            if "taskkill" in block.group(1):
                geschuetzt = True
        self.assertTrue(
            geschuetzt,
            "der taskkill beim Timeout-Abbau steht nicht in einem Abschnitt mit "
            '$ErrorActionPreference = "Continue". Unter "Stop" macht PowerShell '
            "5.1 aus jeder nativen stderr-Zeile einen terminierenden "
            "NativeCommandError — ein haengendes Segment beendet dann den "
            "ganzen Lauf statt nur sich selbst (XPLAT-27).")

    def test_der_runner_faehrt_ueberhaupt_unter_stop(self):
        """Gegenprobe zur Annahme des Tests oben.

        Stuende oben gar kein ``Stop``, waere der geforderte ``Continue``-Block
        ueberfluessig — und dieser Test haette sein Thema verloren, ohne es zu
        merken.
        """
        quelle = RUNNER.read_text(encoding="utf-8", errors="replace")
        self.assertRegex(quelle, r'\$ErrorActionPreference\s*=\s*"Stop"')


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
class LaufUeberlebtEinHaengendesSegmentTest(unittest.TestCase):
    """Verhalten: nach einem Timeout muss es weitergehen.

    ⚠️ **Das Zeitlimit wird GEMESSEN, nicht gesetzt** — und das in zwei Anlaeufen
    gelernt:

    1. Die erste Fassung fuhr ``-TimeoutSec 5``. Sie riss ALLE DREI Segmente,
       auch die trivialen: ein pytest-Start kostet allein schon **6,5 s**
       (conftest kopiert die Geraetebibliothek und startet Qt), bevor die erste
       Zeile Testcode laeuft.
    2. Die zweite stand fest auf 25 s. Allein gruen — im Volllauf rot. Denn
       dieser Test laeuft im Gate als eines von 646 Segmenten unter ``-j 6``,
       und dort ist die Grundlast ein Vielfaches. Wieder liefen die harmlosen
       Dateien ins Zeitlimit, und der Test mass nicht mehr „ueberlebt der Lauf
       einen Haenger", sondern „sind zufaellig alle langsam".

    Beide Male sah der Lauf aus wie ein Nachweis und war keiner. Deshalb wird
    die Grundlast jetzt **hier und jetzt gemessen** und das Zeitlimit daraus
    abgeleitet — allein wie unter Volllast.

    Der Lauf kostet knapp eine Minute und findet deshalb **einmal fuer die
    ganze Klasse** statt — dreimal waere die dreifache Zeit fuer dieselbe
    Messung.
    """

    #: Untergrenze, falls die Messung unplausibel klein ausfaellt.
    TIMEOUT_MIN = 25
    #: Sicherheitsfaktor auf die GEMESSENE Grundlast.
    TIMEOUT_FAKTOR = 4
    _erg = None
    _ausgabe = ""

    @classmethod
    def _grundlast(cls, tmp: Path) -> float:
        """Wie lange braucht ein triviales Segment HIER UND JETZT?

        ★★ Der Grund fuer die Messung statt einer festen Zahl: dieselbe Datei
        laeuft einmal allein und einmal als eines von 646 Segmenten unter
        ``-j 6``. Die zweite Lage ist die, in der dieser Test im Gate wirklich
        stattfindet — und dort ist die Grundlast ein Vielfaches.

        Die erste Fassung stand fest auf 25 s. Sie war allein gruen und im
        Volllauf rot, weil unter Last jedes Segment ueber 25 s brauchte und
        damit auch die beiden HARMLOSEN Dateien ins Zeitlimit liefen. Der Test
        mass dann nicht mehr „ueberlebt der Lauf einen Haenger", sondern „sind
        zufaellig alle langsam" — und war damit genau die Sorte Test, gegen die
        dieses Repo an mehreren Stellen anschreibt.
        """
        probe = tmp / "test_grundlast.py"
        probe.write_text(SCHNELL, encoding="utf-8")
        umgebung = dict(os.environ)
        umgebung["QT_QPA_PLATFORM"] = "offscreen"
        start = time.monotonic()
        subprocess.run([sys.executable, "-m", "pytest", str(probe), "-q",
                        "--no-header", "-p", "no:cacheprovider"],
                       cwd=str(REPO), env=umgebung, capture_output=True,
                       timeout=600)
        probe.unlink(missing_ok=True)
        return time.monotonic() - start

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="lightos_xplat27_")
        tmp = Path(cls._tmp.name)
        gemessen = cls._grundlast(tmp)
        cls.TIMEOUT = max(cls.TIMEOUT_MIN, int(gemessen * cls.TIMEOUT_FAKTOR) + 1)
        # Der Haenger muss das Zeitlimit sicher reissen, auch wenn die Last
        # zwischen Messung und Lauf noch steigt.
        cls.HAENGT_SEK = cls.TIMEOUT * 4
        dateien = []
        for name, inhalt in (("a_schnell", SCHNELL),
                             ("b_haengt", HAENGT.format(sek=cls.HAENGT_SEK)),
                             ("c_schnell", SCHNELL)):
            p = tmp / f"test_{name}.py"
            p.write_text(inhalt, encoding="utf-8")
            dateien.append(str(p))
        umgebung = dict(os.environ)
        # Eigenes Ausgabeverzeichnis: sonst raeumt dieser Lauf die Ergebnisse
        # eines aeusseren Gate-Laufs ab (die QA-53-Falle).
        umgebung["LIGHTOS_SEG_OUT"] = str(tmp / "out")
        umgebung["QT_QPA_PLATFORM"] = "offscreen"
        cls._erg = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(RUNNER), "-TimeoutSec", str(cls.TIMEOUT), "-j", "1",
             *dateien],
            cwd=str(REPO), env=umgebung, capture_output=True, timeout=900)
        cls._ausgabe = (cls._erg.stdout + cls._erg.stderr).decode("utf-8", "replace")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_die_datei_nach_dem_haenger_wird_noch_gefahren(self):
        """★ Die eigentliche Aussage.

        ``c_schnell`` steht hinter dem Haenger. Taucht sie in der Ausgabe nicht
        auf, ist der Lauf am Timeout gestorben — genau der Vorfall.
        """
        ausgabe = self._ausgabe
        self.assertIn("test_c_schnell", ausgabe,
                          "die Datei hinter dem haengenden Segment wurde nicht "
                          f"mehr gefahren — der Lauf ist abgebrochen:\n"
                          f"{ausgabe[-1500:]}")

    def test_der_haenger_wird_als_zeit_gemeldet_und_nicht_verschwiegen(self):
        """Ein abgebrochenes Segment muss SICHTBAR sein.

        Stiller Abbau waere schlimmer als der Abbruch: dann faehrt das Gate
        durch und meldet gruen, obwohl eine Datei nie zu Ende lief.
        """
        ausgabe = self._ausgabe
        self.assertIn("test_b_haengt", ausgabe, ausgabe[-1200:])
        self.assertRegex(ausgabe, r"ZEIT|zeit|abgebrochen",
                         "der Haenger wurde nicht als Zeitueberschreitung "
                         f"gemeldet:\n{ausgabe[-1200:]}")

    def test_der_haenger_wird_nicht_als_bestanden_gezaehlt(self):
        """Er darf nicht in die Gruen-Zahl rutschen.

        ⚠️ **Nicht geprueft wird der Exit-Code** — und das ist eine Korrektur an
        der ersten Fassung dieses Tests. Sie verlangte Exit != 0 und war rot;
        der Grund steht ausdruecklich im Runner:

            „Exit-Vertrag wie run_tests.ps1 -Isolate: NUR echte Test-Failures
             faerben rot. Crashes/Timeouts sind Umgebungs-Flakiness."

        Das ist eine bewusste Entscheidung, keine Luecke, und der Kopf des
        Skripts warnt ausdruecklich davor, sie ohne Messung zu drehen. Ein Test,
        der sie umstoesst, waere kein Waechter, sondern eine stille
        Meinungsaenderung.

        Was hier trotzdem gilt und geprueft wird: der Haenger darf nicht als
        BESTANDEN gezaehlt werden. „Nicht rot" und „gruen" sind zweierlei.

        ★ Ob die Toleranz fuer Timeouts genauso begruendet ist wie die fuer
        Crashes, ist eine offene Frage — die Begruendung im Kopf traegt fuer
        Crashes (nativer Abbau NACH bestandenen Tests), fuer ein Segment, das
        gar nicht zu Ende lief, aber nicht ohne Weiteres. Als Befund erfasst,
        nicht hier entschieden.
        """
        ausgabe = self._ausgabe
        m = re.search(r"\[seg\]\s+(\d+)/(\d+)\s+Segmente gruen", ausgabe)
        self.assertIsNotNone(m, f"keine Bilanzzeile gefunden:\n{ausgabe[-1200:]}")
        gruen, gesamt = int(m.group(1)), int(m.group(2))
        self.assertEqual(3, gesamt, "es waren drei Dateien")
        self.assertEqual(2, gruen,
                         "der Haenger wurde als bestanden gezaehlt — dann "
                         "meldet das Gate mehr, als es gemessen hat")


if __name__ == "__main__":
    unittest.main()
