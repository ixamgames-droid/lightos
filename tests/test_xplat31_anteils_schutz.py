"""XPLAT-31: kein einziges gruenes Segment darf nie Exit 0 ergeben.

**Woher der Punkt kommt.** Beim Testbau zu XPLAT-27 lief ein Gate-Lauf, in dem
JEDES der drei Segmente ins Zeitlimit fiel. Er meldete ``0/3 Segmente gruen``
und trotzdem **Exit 0**. Ein Mensch liest „0 von 3 gruen" als rot; das Gate
sagte das Gegenteil.

**Warum das kein Widerspruch zur Timeout-Toleranz ist** (XPLAT-28, dort
ausfuehrlich begruendet): jene Toleranz gilt dem EINZELFALL — ein Segment, das
nach bestandenen Tests nativ abbaut oder haengt. Sie war nie eine Aussage ueber
einen ganzen Lauf. Ist kein einziges Segment gruen, ist das keine Flakiness,
sondern eine kaputte Umgebung: kein venv, keine Bibliothek, ein Prozess der
jede Datei blockiert.

Der Schutz ist deshalb als **Anteil** formuliert und nicht als Aenderung der
Einzelregel — die begruendete Toleranz bleibt vollstaendig erhalten.

★ **Auf Linux gibt es den Fall nicht**, weil ``verify_segmented.sh`` jeden
``rc != 0`` rot zaehlt: sind alle Segmente auffaellig, ist ``BAD > 0``. Diese
Datei stellt also Gleichstand her und fuehrt nichts Neues ein — deshalb prueft
sie auch nur die Windows-Seite.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "tools" / "verify_segmented.ps1"

_PLAT = sys.platform
_IST_WINDOWS = _PLAT == "win32"
_GRUND = ("verify_segmented.ps1 ist das Windows-Gate; auf Linux zaehlt "
          "verify_segmented.sh jeden rc != 0 rot, der Fall entsteht dort nicht")

#: Siehe XPLAT-27: dieser Test startet selbst einen Runner. Im Volllauf waere
#: das ein Gate IM Gate (QA-53), und der innere Lauf scheitert dort
#: reproduzierbar. Beide Runner setzen das Merkmal seit XPLAT-27.
_IM_SEGMENT = bool(os.environ.get("LIGHTOS_IM_SEGMENT"))
_SEGMENT_GRUND = (
    "startet selbst einen Segment-Runner — im Volllauf waere das ein Gate IM "
    "Gate (QA-53). Gezielter Nachweis: "
    ".\\tools\\verify_loop.ps1 tests\\test_xplat31_anteils_schutz.py")

GRUEN = "def test_gruen():\n    assert True\n"
ROT = "def test_rot():\n    assert False\n"


class ExitVertragStehtImSkriptTest(unittest.TestCase):
    """Statisch — laeuft auf JEDER Plattform und in JEDEM Lauf."""

    def test_der_anteils_schutz_ist_verdrahtet(self):
        """``$okCount -eq 0`` muss im Exit-Zweig vorkommen.

        Der Verhaltenstest unten kann im Volllauf nicht laufen; dieser hier
        schon. Er ist damit der eigentliche Waechter gegen ein stilles
        Zurueckdrehen.
        """
        quelle = RUNNER.read_text(encoding="utf-8", errors="replace")
        self.assertRegex(
            quelle, r"\$okCount\s*-eq\s*0",
            "der Anteils-Schutz aus XPLAT-31 fehlt: ein Lauf ohne ein einziges "
            "gruenes Segment wuerde wieder Exit 0 melden")

    def test_die_einzelfall_toleranz_ist_nicht_mitgerissen(self):
        """★ Gegenprobe zur Absicht.

        XPLAT-31 darf die begruendete Toleranz aus XPLAT-28 NICHT aufheben —
        sonst waere aus einem Anteils-Schutz eine Aenderung der Einzelregel
        geworden, und genau das sollte er vermeiden. Der Exit-Zweig muss also
        weiterhin allein an ``$fail`` haengen.
        """
        quelle = RUNNER.read_text(encoding="utf-8", errors="replace")
        self.assertRegex(quelle, r"if\s*\(\$fail\.Count\)\s*\{\s*exit 1\s*\}",
                         "die Failure-Regel wurde umgebaut statt ergaenzt")
        self.assertNotRegex(
            quelle, r"if\s*\(\$fail\.Count\s*-or\s*\$timeout\.Count\)",
            "Timeouts faerben jetzt pauschal rot — das ist die Aenderung, die "
            "XPLAT-28 nach Messung ausdruecklich verworfen hat")


@unittest.skipUnless(_IST_WINDOWS, _GRUND)
@unittest.skipIf(_IM_SEGMENT, _SEGMENT_GRUND)
class LaufOhneGruenesSegmentIstRotTest(unittest.TestCase):
    """Verhalten am echten Runner."""

    def _lauf(self, inhalte, timeout_sek=None):
        """Runner mit eigenen Testdateien fahren.

        ``timeout_sek`` unter der Grundlast eines Segments (~6,5 s: Prozess-
        start + conftest) laesst ALLE Segmente ins Zeitlimit laufen. Das ist
        hier kein Versehen, sondern der einzige billige Weg, Segmente zu
        erzeugen, die WEDER gruen NOCH ``$fail`` sind — genau die Lage, die der
        Anteils-Schutz abdeckt. (In XPLAT-27 war dasselbe Verhalten ein Fehler,
        weil dort der Haenger allein ins Limit laufen sollte.)
        """
        with tempfile.TemporaryDirectory(prefix="lightos_xplat31_") as tmp:
            tmp = Path(tmp)
            dateien = []
            for i, inhalt in enumerate(inhalte):
                p = tmp / f"test_{i}_probe.py"
                p.write_text(inhalt, encoding="utf-8")
                dateien.append(str(p))
            umgebung = dict(os.environ)
            for schluessel in ("LIGHTOS_LOCKFILE", "LIGHTOS_VERIFY_DRYRUN",
                               "LIGHTOS_VERIFY_NOLOCK", "LIGHTOS_VERIFY_SINGLE"):
                umgebung.pop(schluessel, None)
            umgebung["LIGHTOS_SEG_OUT"] = str(tmp / "out")
            umgebung["LIGHTOS_SHOW_DB"] = str(tmp / "kind_show.db")
            umgebung["QT_QPA_PLATFORM"] = "offscreen"
            argumente = ["-j", "1"]
            if timeout_sek is not None:
                argumente += ["-TimeoutSec", str(timeout_sek)]
            erg = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(RUNNER), *argumente, *dateien],
                cwd=str(REPO), env=umgebung, capture_output=True, timeout=900)
            return erg.returncode, (erg.stdout + erg.stderr).decode("utf-8", "replace")

    def test_alle_segmente_rot_ergibt_rot(self):
        """Der Normalfall — der war auch vorher schon rot (``$fail``)."""
        rc, ausgabe = self._lauf([ROT, ROT])
        self.assertNotEqual(0, rc, ausgabe[-800:])

    def test_ein_gruenes_segment_genuegt_fuer_gruen(self):
        """★ POSITIVKONTROLLE, und sie ist hier die wichtigere Haelfte.

        Ohne sie koennte der Anteils-Schutz pauschal rot faerben und alle Tests
        oben blieben gruen — aus dem Schutz waere dann die Aenderung der
        Einzelregel geworden, die XPLAT-28 nach Messung verworfen hat.
        """
        rc, ausgabe = self._lauf([GRUEN, GRUEN])
        self.assertEqual(0, rc, ausgabe[-800:])

    def test_nur_zeitlimits_und_kein_gruenes_segment_ergibt_ROT(self):
        """★★ Der eigentliche Nachweis — der Fall, den es vorher nicht gab.

        Zwei GESUNDE Testdateien, aber ein Zeitlimit unter der Grundlast: beide
        Segmente landen in ``$timeout``, keines in ``$fail``, keines ist gruen.
        **Vor XPLAT-31 meldete genau das Exit 0.**

        Die erste Fassung dieses Tests fuhr stattdessen zwei ROTE Dateien — und
        traf damit den ``$fail``-Zweig, also den Weg, der ohnehin schon rot war.
        Er waere auch ohne den Anteils-Schutz gruen geblieben und haette nichts
        bewiesen.
        """
        rc, ausgabe = self._lauf([GRUEN, GRUEN], timeout_sek=3)
        self.assertRegex(ausgabe, r"0/2 Segmente gruen",
                         f"die Vorbedingung stimmt nicht — es war doch ein "
                         f"Segment gruen:\n{ausgabe[-800:]}")
        self.assertRegex(ausgabe, r"0 Failures",
                         f"die Segmente landeten in $fail statt im Zeitlimit — "
                         f"dann prueft dieser Test den falschen Zweig:\n"
                         f"{ausgabe[-800:]}")
        self.assertNotEqual(0, rc,
                            "kein einziges gruenes Segment, trotzdem Exit 0 — "
                            f"der Anteils-Schutz greift nicht:\n{ausgabe[-800:]}")
        self.assertRegex(ausgabe, r"KEIN EINZIGES|kaputte Umgebung",
                         "rot allein hilft am Rechner nicht — es muss "
                         f"dabeistehen, wonach man sucht:\n{ausgabe[-800:]}")


if __name__ == "__main__":
    unittest.main()
