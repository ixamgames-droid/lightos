"""QA-93: das Gate oeffnet kein echtes Fenster.

Befund (Windows-Testrechner, 2026-10-10): bei JEDEM Voll-Gate erschien einmal
ein bildschirmfuellendes Fenster „python“ — mitgeschrieben 1550x878 ab (0,0),
10,1 Sekunden lang —, waehrend am Rechner gearbeitet wurde. Es kam aus
``tests/test_viz_render_benchmark.py``: der Test rief
``tools/viz_render_benchmark.py 32 --runden 32 --aus kegel`` als Prozess auf, um
zu pruefen, wie das Werkzeug seine Zeile liest. Das Werkzeug loescht
``QT_QPA_PLATFORM`` (es MUSS in einem echten Fenster messen, offscreen misst die
CPU) — ``QT_QPA_PLATFORM=offscreen`` im Aufruf half also nichts, und ein
gueltiger Aufruf war eine echte Messung.

Unter Linux ohne Bildschirm fiel das nicht auf: der Prozess scheiterte dort am
fehlenden Display, und der Test fragte nur, ob ein bestimmter Abbruchtext
FEHLT.

Jetzt: ``--plan`` zeigt, was gemessen wuerde, und endet vor jedem Fenster; die
Tests rufen das Werkzeug nur noch so auf.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"
TESTS = REPO / "tests"
WERKZEUG = TOOLS / "viz_render_benchmark.py"

#: Kind: das Werkzeug als ``__main__`` ausfuehren und danach nachsehen, ob dabei
#: eine Qt-Anwendung entstanden ist. Ohne Anwendung gibt es kein Fenster.
_KIND = r"""
import json, runpy, sys
sys.argv = [sys.argv[1]] + sys.argv[2:]
code = 0
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit as e:
    code = e.code
qt = sys.modules.get("PySide6.QtCore")
app = qt.QCoreApplication.instance() if qt is not None else None
print("\nKIND " + json.dumps({"exit": code if isinstance(code, int) or code is None else str(code),
                              "qt_anwendung": app is not None}))
"""


def _kind(*argv) -> tuple[dict, str]:
    r = subprocess.run([sys.executable, "-c", _KIND, str(WERKZEUG), *argv],
                       cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    zeilen = [z for z in r.stdout.splitlines() if z.startswith("KIND ")]
    assert zeilen, (r.returncode, r.stdout[-800:], r.stderr[-800:])
    return json.loads(zeilen[-1][5:]), r.stdout


class PlanOhneFensterTest(unittest.TestCase):

    def test_plan_endet_ohne_qt_anwendung(self):
        stand, aus = _kind("32", "--runden", "32", "--aus", "kegel", "--plan")
        self.assertIn(stand["exit"], (0, None), aus[-600:])
        self.assertFalse(stand["qt_anwendung"],
                         "--plan hat eine Qt-Anwendung gebaut — von dort ist es "
                         "ein Schritt zum Fenster")
        plan = json.loads([z for z in aus.splitlines() if z.startswith("{")][0])
        self.assertEqual(plan["stufen"], [32])
        self.assertEqual(plan["runden"], 32)
        self.assertEqual(plan["aus"], "kegel")

    def test_abbrueche_liegen_weiter_vor_jedem_fenster(self):
        for argv in (("12", "32", "--aus", "kegel"), ("32", "--runden"), ("--aus", "schatten")):
            with self.subTest(argv=argv):
                stand, _aus = _kind(*argv)
                self.assertNotIn(stand["exit"], (0, None), "der Aufruf lief durch")
                self.assertFalse(stand["qt_anwendung"])

    def test_plan_ist_dokumentiert(self):
        self.assertIn("--plan", WERKZEUG.read_text(encoding="utf-8").split('"""')[1])


class KeinTestMisstImEchtenFensterTest(unittest.TestCase):
    """Stolperdraht fuer die naechste solche Stelle."""

    #: Werkzeuge, die die Offscreen-Vorgabe des Testlaufs verwerfen, weil sie
    #: ein echtes Fenster brauchen.
    _VERWIRFT = re.compile(r"""os\.environ\.pop\(\s*["']QT_QPA_PLATFORM["']""")

    #: Tests, die ein solches Werkzeug als Prozess starten — und warum dabei
    #: kein Fenster entsteht. Wer hier etwas eintraegt, hat es nachgesehen.
    BEKANNT = {
        "test_viz_render_benchmark.py":
            "ruft nur ueber _lauf(), und _lauf() haengt --plan an (QA-93)",
        "test_qa93_gate_ohne_echtes_fenster.py":
            "prueft genau das: --plan und die Abbrueche bauen keine Qt-Anwendung",
        "test_tool16_stage_reload_kein_port.py":
            "laedt verify_stage_reload als Modul in einem eigenen Kind (nicht als "
            "__main__ — nur dort wird die Offscreen-Vorgabe verworfen) und endet "
            "vor dem Fenster",
        "test_qa58_bibliothek_schema_unberuehrt.py":
            "nennt verify_stage_reload nur in einem Kommentar",
    }

    def _echte_fenster_werkzeuge(self) -> list[str]:
        return sorted(p.name for p in TOOLS.glob("*.py")
                      if self._VERWIRFT.search(p.read_text(encoding="utf-8", errors="replace")))

    def test_die_suche_findet_das_messwerkzeug(self):
        self.assertIn("viz_render_benchmark.py", self._echte_fenster_werkzeuge())

    def test_nur_bekannte_tests_starten_ein_solches_werkzeug(self):
        werkzeuge = self._echte_fenster_werkzeuge()
        neu = []
        for test in sorted(TESTS.glob("test_*.py")):
            text = test.read_text(encoding="utf-8", errors="replace")
            if "subprocess" not in text:
                continue
            for w in werkzeuge:
                if w in text and test.name not in self.BEKANNT:
                    neu.append(f"{test.name} -> tools/{w}")
        self.assertEqual(
            neu, [],
            "Diese Tests starten ein Werkzeug, das ein ECHTES Fenster oeffnet "
            "(es loescht QT_QPA_PLATFORM). Im Gate erscheint das auf dem "
            "Bildschirm dessen, der am Rechner arbeitet. Das Werkzeug so "
            "aufrufen, dass es vor dem Fenster endet (--plan o. ae.), und den "
            "Test mit Begruendung in BEKANNT eintragen:\n  " + "\n  ".join(neu))

    def test_der_benchmark_test_ruft_nur_mit_plan(self):
        text = (TESTS / "test_viz_render_benchmark.py").read_text(encoding="utf-8")
        aufrufe = re.findall(r"subprocess\.(?:run|Popen|check_output|call)\(\s*\[([^\]]*)\]", text)
        self.assertTrue(aufrufe, "kein Prozessaufruf gefunden — Suche laeuft leer")
        for a in aufrufe:
            if "_WERKZEUG" in a:
                self.assertIn('"--plan"', a, f"Aufruf ohne --plan: [{a}]")


if __name__ == "__main__":
    unittest.main()
