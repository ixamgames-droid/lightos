"""QA-118 (a): ein ``@unittest.skip...``-Dekorator muss eine Klasse oder einen Test treffen.

**Der Befund (15.11.2026, Windows x64).** QA-117 (#1268) hat in
``tests/test_proc02c_webengine_sperre.py`` eine Hilfsfunktion zwischen
``@unittest.skipUnless(_LAEUFT, _GRUND)`` und die Testklasse gesetzt. Python
haengt einen Dekorator an das NAECHSTE ``def``/``class`` - der Skip traf die
Hilfsfunktion, die Klasse lief ungeschuetzt. Unter Linux merkt man nichts
(dort ist die Bedingung wahr), unter Windows waren drei Tests rot: ``bash`` und
``flock`` gibt es dort nicht. Aufgefallen ist es nur im vollen Windows-Gate.

Der Waechter liest jede Testdatei per ``ast`` und meldet jede Funktion auf
Modulebene, die NICHT mit ``test`` beginnt und trotzdem einen Skip-Dekorator
traegt. So eine Funktion ruft pytest nie als Test auf - der Dekorator sitzt
also fast sicher an der falschen Stelle. Das gilt auf jeder Plattform, der
Waechter ist deshalb auch unter Linux rot.
"""
from __future__ import annotations

import ast
import unittest
import warnings
from pathlib import Path

TESTS = Path(__file__).resolve().parent

_SKIP_NAMEN = {"skip", "skipIf", "skipUnless"}


def _ist_skip(dekorator: ast.expr) -> bool:
    """``@unittest.skip...(...)``, ``@skipUnless(...)`` usw."""
    ziel = dekorator.func if isinstance(dekorator, ast.Call) else dekorator
    if isinstance(ziel, ast.Attribute):
        return ziel.attr in _SKIP_NAMEN and isinstance(ziel.value, ast.Name) \
            and ziel.value.id == "unittest"
    return isinstance(ziel, ast.Name) and ziel.id in _SKIP_NAMEN


def verrutschte_skips(quelltext: str) -> list[str]:
    """Namen der Funktionen auf Modulebene, die einen Skip tragen, aber kein Test sind."""
    with warnings.catch_warnings():
        # Fremde Dateien mit z. B. '\s' in normalen Strings: nicht unser Thema.
        warnings.simplefilter("ignore", SyntaxWarning)
        baum = ast.parse(quelltext)
    return [knoten.name for knoten in baum.body
            if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not knoten.name.startswith("test")
            and any(_ist_skip(d) for d in knoten.decorator_list)]


class SkipTrifftKlasseTest(unittest.TestCase):

    def test_kein_skip_dekorator_auf_einer_hilfsfunktion(self):
        funde = {}
        for datei in sorted(TESTS.glob("test_*.py")):
            namen = verrutschte_skips(datei.read_text(encoding="utf-8"))
            if namen:
                funde[datei.name] = namen
        self.assertEqual({}, funde,
                         "Skip-Dekorator vor einer Hilfsfunktion - er gehoert vor die "
                         "Klasse bzw. den Test darunter (QA-118)")

    def test_waechter_erkennt_den_fall_aus_qa117(self):
        """Positivkontrolle: genau die Form, die #1268 hatte."""
        quelle = ("import unittest\n"
                  "@unittest.skipUnless(False, 'x')\n"
                  "\n"
                  "def _hilfe():\n"
                  "    pass\n"
                  "\n"
                  "class T(unittest.TestCase):\n"
                  "    def test_a(self):\n"
                  "        pass\n")
        self.assertEqual(["_hilfe"], verrutschte_skips(quelle))

    def test_waechter_laesst_richtige_faelle_in_ruhe(self):
        quelle = ("import unittest\n"
                  "from unittest import skipIf\n"
                  "@unittest.skipUnless(False, 'x')\n"
                  "class T(unittest.TestCase):\n"
                  "    pass\n"
                  "@skipIf(True, 'y')\n"
                  "def test_frei():\n"
                  "    pass\n"
                  "def _hilfe():\n"
                  "    pass\n")
        self.assertEqual([], verrutschte_skips(quelle))


if __name__ == "__main__":
    unittest.main()
