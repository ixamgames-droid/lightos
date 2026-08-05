"""VC-AUTOPOS — skript-gebaute VC-Seiten stapelten alle Widgets auf (0,0).

Gefunden, als David die frisch gebaute ZQ06121-Demo öffnete: *„irgendwie ist die
VC leer"*, kurz darauf *„die waren alle oben links in der Ecke"*.

`ShowBuilder._add` setzte nie eine Position. Die bestehenden Build-Skripte
umgehen das, indem sie `setGeometry` **von Hand** rufen — wer das vergisst,
bekommt eine Seite, die aussieht als wäre sie leer, obwohl jede Bindung stimmt.

★ WARUM KEIN VORHANDENES GATE DAS SAH
`lint_show.py --strict` prüft Bindungen, Enums und Parameter — aber **keine
Geometrie**. Eine Show kann vollständig gültig sein und trotzdem unbedienbar.
Genau diese Lücke schliesst dieser Test.

Dazu die zwei anderen Funde derselben Runde:
- Der Render-Smoke prüfte fest Universum 1 (`TOOL-RENDERUNI`).
- `main.py --show` lädt eine Show direkt beim Start (`TOOL-SHOWARG`).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import pytest as _pytest_xplat15                          # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets   # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app():
    return QApplication.instance() or QApplication([])


def _builder():
    from src.core.show.showbuilder.builder import ShowBuilder
    _app()
    return ShowBuilder(reset=True)


def _rechteck(w):
    g = w.geometry()
    return (g.x(), g.y(), g.width(), g.height())


class AutoPositionTest(unittest.TestCase):

    def test_taster_stapeln_sich_nicht(self):
        b = _builder()
        knoepfe = [b.label(f"L{i}", bank=0) for i in range(6)]
        stellen = {(_rechteck(w)[0], _rechteck(w)[1]) for w in knoepfe}
        self.assertEqual(len(stellen), 6,
                         f"Widgets liegen uebereinander: {sorted(stellen)}")

    def test_keine_ueberlappung_bei_vielen_widgets(self):
        # Die Demo hat 38 Widgets — das ist der Fall, der es aufgedeckt hat.
        b = _builder()
        ws = [b.label(f"L{i}", bank=i % 3) for i in range(38)]
        proBank = {}
        for w in ws:
            proBank.setdefault(w.bank, []).append(_rechteck(w))
        for bank, rechtecke in proBank.items():
            ecken = {(r[0], r[1]) for r in rechtecke}
            self.assertEqual(len(ecken), len(rechtecke),
                             f"Bank {bank}: doppelte Positionen")

    def test_jede_bank_faengt_wieder_links_oben_an(self):
        # Sonst waere Seite 2 nach rechts verschoben, ohne dass jemand das will.
        b = _builder()
        a = b.label("A", bank=0)
        c = b.label("C", bank=1)
        self.assertEqual(_rechteck(a)[:2], _rechteck(c)[:2])

    def test_eigene_geometrie_gewinnt(self):
        # Bestandsschutz: die vorhandenen Build-Skripte positionieren selbst.
        b = _builder()
        w = b.label("X", bank=0)
        w.setGeometry(700, 400, 120, 40)
        self.assertEqual(_rechteck(w), (700, 400, 120, 40))

    def test_regler_bekommen_reglermasse(self):
        # Ein Regler in Tastergroesse ist unbedienbar — 90x230 ist das Mass,
        # das die handgebauten Seiten benutzen.
        b = _builder()
        s = b.slider("Master", mode="GrandMaster", bank=0)
        _x, _y, breit, hoch = _rechteck(s)
        self.assertEqual((breit, hoch), (90, 230))

    def test_widgets_liegen_im_sichtbaren_bereich(self):
        # Negative oder absurd grosse Koordinaten waeren dasselbe Problem in
        # gruen: das Widget existiert, man sieht es nur nicht.
        b = _builder()
        for i in range(30):
            w = b.label(f"L{i}", bank=0)
            x, y, _b, _h = _rechteck(w)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLess(x, 4000, "x laeuft aus jedem Fenster")
            self.assertLess(y, 4000, "y laeuft aus jedem Fenster")


class RenderSmokeUniversumTest(unittest.TestCase):
    """TOOL-RENDERUNI: der Smoke muss dort messen, wo die Geraete haengen."""

    def test_build_and_verify_reicht_das_universum_durch(self):
        import inspect
        from tools._builder import build_and_verify
        sig = inspect.signature(build_and_verify)
        self.assertIn("universe", sig.parameters,
                      "ohne diesen Parameter misst der Smoke immer Universum 1")
        self.assertEqual(sig.parameters["universe"].default, 1,
                         "Vorgabe muss 1 bleiben — Bestandsskripte")

    def test_render_diff_kennt_andere_universen(self):
        import inspect
        from src.core.capability.render_probe import render_diff
        self.assertEqual(
            inspect.signature(render_diff).parameters["universe"].default, 1)


class ShowArgumentTest(unittest.TestCase):
    """TOOL-SHOWARG: `main.py --show <datei>`."""

    def test_hilfe_nennt_das_argument(self):
        import subprocess
        import sys
        aus = subprocess.run(
            [sys.executable, "main.py", "--help"],
            capture_output=True, text=True, timeout=120,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertIn("--show", aus.stdout)

    def test_fehlender_pfad_wird_sofort_gemeldet(self):
        # Der Punkt: NICHT erst nach dem Hochfahren still scheitern, sonst
        # steht die alte Show da und man sucht den Fehler in der Show.
        import subprocess
        import sys
        aus = subprocess.run(
            [sys.executable, "main.py", "--show", "gibtesnicht.lshow"],
            capture_output=True, text=True, timeout=120,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertNotEqual(aus.returncode, 0)
        self.assertIn("nicht gefunden", aus.stderr)

    def test_geladen_wird_ueber_den_ui_pfad(self):
        # `load_show` allein fuellt nur den Zustand — Fenstertitel,
        # Zuletzt-benutzt-Liste und Render-Schalter haengen an
        # `_open_show_path`. Sonst zeigt die Oberflaeche weiter die alte Show.
        import inspect
        import main as hauptmodul
        quelle = inspect.getsource(hauptmodul._open_show_at_startup)
        self.assertIn("_open_show_path", quelle)
        self.assertIn("singleShot", quelle,
                      "vor dem Start der Ereignisschleife sind die Views halb gebaut")


if __name__ == "__main__":
    unittest.main()
