"""PROC-05 — die Aufraeum-Fixture darf nicht ueber ``allWidgets()`` laufen.

Der Befund
----------
``QApplication.allWidgets()`` baut eine Liste ueber ALLE lebenden QWidgets —
auch ueber die, deren C++-Seite schon fort ist, waehrend der Python-Wrapper noch
existiert. Beim Bauen dieser Liste stirbt der Prozess mit SIGSEGV. Gemessen an
``tests/test_viz10_ui_repairs.py`` auf unveraendertem ``main``: **5 von 6 Laeufen**
``exit 139``, Traceback jedes Mal auf der ``allWidgets()``-Zeile — mitten im Lauf,
im Teardown des ERSTEN Tests. Nach dem Umbau: **0 von 6**.

★ Nicht zu verwechseln mit PROC-04. Der Absturz dort lag in der Interpreter-
Abbauphase und wurde von ``LIGHTOS_HARDEN_EXIT_ALL`` (#662) erschlagen; dieser
tritt mit derselben Variable weiter auf (2 von 3 gemessen). Gleicher Exit-Code,
andere Ursache.

Was dieser Test misst
---------------------
Der Absturz selbst laesst sich nicht als Zusicherung schreiben — ein SIGSEGV
beendet den Prozess, es gibt kein ``assert``, das ihn ueberlebt. Messbar ist
stattdessen das, was den Absturz ausloest bzw. verhindert:

1. Die Fixture ruft ``allWidgets()`` **nicht mehr** (Textprobe an der echten
   ``conftest.py`` — die Gefahr steckt im Aufruf, nicht in seinem Ergebnis).
2. Der Ersatz findet **dieselben** Objekte. Das ist die eigentliche Gefahr bei
   dieser Art Fix: „nichts finden" macht jeden Absturz weg und laesst den
   Aufraeumer wirkungslos zurueck. Genau deshalb steht der Positivnachweis hier
   vor dem Negativnachweis.
3. Ein halbtoter Wrapper laesst den Ersatz nicht abstuerzen, sondern wird
   uebersprungen.
"""
import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget      # noqa: E402

from conftest import _lebende_canvases                   # noqa: E402
from src.ui.virtualconsole.vc_canvas import VCCanvas     # noqa: E402

_app = QApplication.instance() or QApplication([])

CONFTEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conftest.py")


class FindetDieselbenObjekteTest(unittest.TestCase):
    """Positivkontrolle zuerst: ein Aufraeumer, der nichts findet, stuerzt auch
    nicht ab — und raeumt nichts auf."""

    def setUp(self):
        self._muell = []

    def tearDown(self):
        for w in self._muell:
            w.deleteLater()
        self._muell.clear()
        _app.processEvents()

    def _canvas(self, parent=None):
        c = VCCanvas(parent)
        self._muell.append(c)
        return c

    def test_findet_einen_parentlosen_canvas(self):
        c = self._canvas()
        self.assertIn(c, _lebende_canvases(_app, VCCanvas))

    def test_findet_einen_canvas_TIEF_unter_einem_fenster(self):
        # Der Produktionsfall: der Canvas haengt in der VirtualConsoleView,
        # die im Hauptfenster haengt. Wer nur die Top-Level-Widgets ansieht,
        # findet ihn NICHT — und raeumt im Betrieb nie etwas auf.
        fenster = QWidget()
        self._muell.append(fenster)
        zwischen = QWidget(fenster)
        c = self._canvas(zwischen)
        self.assertIn(c, _lebende_canvases(_app, VCCanvas))

    def test_findet_mehrere_und_jeden_nur_einmal(self):
        fenster = QWidget()
        self._muell.append(fenster)
        a, b = self._canvas(), self._canvas(fenster)
        gefunden = _lebende_canvases(_app, VCCanvas)
        self.assertIn(a, gefunden)
        self.assertIn(b, gefunden)
        self.assertEqual(len(gefunden), len(set(id(x) for x in gefunden)))

    def test_gewoehnliche_widgets_kommen_NICHT_mit(self):
        # Sonst rufe der Aufraeumer ``_teardown_midi`` auf Objekten, die das
        # gar nicht haben — und der try/except darum verschluckte es still.
        fremd = QWidget()
        self._muell.append(fremd)
        self.assertNotIn(fremd, _lebende_canvases(_app, VCCanvas))


class HalbtoterWrapperTest(unittest.TestCase):
    def test_ein_geloeschtes_top_level_widget_bringt_den_ersatz_nicht_um(self):
        """Das Szenario, das ``allWidgets()`` zum Absturz bringt.

        Hier kommt es als ``RuntimeError`` zurueck — die Rueckmeldung, die
        ``allWidgets()`` einem nicht gibt, weil es den Prozess vorher beendet.
        """
        from shiboken6 import Shiboken

        w = QWidget()
        c = VCCanvas(w)
        Shiboken.delete(w)                    # C++-Seite fort, Wrapper bleibt
        self.assertFalse(Shiboken.isValid(w))
        # Darf weder werfen noch abstuerzen; der tote Zweig faellt einfach weg.
        gefunden = _lebende_canvases(_app, VCCanvas)
        self.assertNotIn(c, gefunden)
        # …und ein GESUNDER Canvas wird daneben trotzdem gefunden.
        gesund = VCCanvas()
        try:
            self.assertIn(gesund, _lebende_canvases(_app, VCCanvas))
        finally:
            gesund.deleteLater()
            _app.processEvents()


class DieFixtureRuftEsNichtMehrTest(unittest.TestCase):
    """Textprobe an der ECHTEN conftest.py.

    Die Gefahr steckt im AUFRUF, nicht in seinem Ergebnis — ein Test, der nur
    das Ergebnis prueft, koennte den Aufruf nicht sehen. Deshalb hier der Blick
    in die Datei, eng auf die eine Fixture begrenzt.
    """

    def _fixture_quelltext(self) -> str:
        with open(CONFTEST, encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"def _cleanup_vc_canvases\(\):(.*?)(?=\n@pytest\.fixture)",
                      text, re.S)
        self.assertIsNotNone(m, "Fixture _cleanup_vc_canvases nicht gefunden")
        return m.group(1)

    def test_die_fixture_ruft_kein_allWidgets(self):
        self.assertNotIn("allWidgets", self._fixture_quelltext())

    def test_die_fixture_raeumt_ueberhaupt_noch_auf(self):
        # Ohne das waere „ruft kein allWidgets" auch dann erfuellt, wenn jemand
        # den Rumpf einfach geleert haette.
        rumpf = self._fixture_quelltext()
        self.assertIn("_teardown_midi", rumpf)
        self.assertIn("_lebende_canvases", rumpf)


if __name__ == "__main__":
    unittest.main()
