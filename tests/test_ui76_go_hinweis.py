"""UI-76: GO-Hinweis nennt die aktuelle Page zuerst; der Bindungs-Hinweis veraltet nicht.

Codex-Review #921 (P2): liegt dieselbe Cueliste auf Executoren MEHRERER Pages,
lieferte ``executor_von`` die erste Bindung in Page-Reihenfolge. Lag die auf
einer frueheren Page, meldete GO „liegt auf Page 1, Ex 4“ — obwohl die Liste
auch in der sichtbaren Executor-Leiste der aktuellen Page liegt.

Codex-Review #836 (P2): nach „„X“ liegt jetzt auf Ex 1“ blieb der Hinweis
stehen, wenn der Bediener die Belegung danach im Auswahlfeld des Executors von
Hand aenderte („— Leer —“ oder eine andere Liste) — er behauptete weiter eine
Bindung, die es nicht mehr gab.

Echter AppState + echte PlaybackView (offscreen), Aufbau wie test_ui68.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.cueliste_ziel import executor_von
from src.core.engine.cue import Cue
from src.ui.views.playback_view import PlaybackView

_app = QApplication.instance() or QApplication([])


class _Statusleiste:
    def __init__(self):
        self.meldungen = []

    def showMessage(self, text, timeout=0):
        self.meldungen.append(text)


class _Fenster:
    def __init__(self):
        self._leiste = _Statusleiste()

    def statusBar(self):
        return self._leiste


class GoHinweisTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.pe = self.state.playback_engine
        self._orig_stacks = list(self.state.cue_stacks)
        self._orig_page = self.pe.current_page
        self._orig_bindung = [[(ex.stack, ex.label, ex.fader_value,
                                ex.fader_function) for ex in page]
                              for page in self.pe.pages]
        self.state.cue_stacks.clear()
        self.state.gewaehlte_cueliste = None
        self.pe.current_page = 0
        for page in self.pe.pages:
            for ex in page:
                ex.stack = None
                ex.label = f"Exec {ex.slot}"
                ex.fader_value = 1.0
                ex.fader_function = "volume"
        self.liste = self.state.new_cue_stack("Neue Liste")
        self.liste.add_cue(Cue(number=1.0, fade_in=0.0, values={1: {"intensity": 128}}))
        self.view = PlaybackView()
        self.view._combo_stack.setCurrentIndex(0)
        self.assertIs(self.view._current_stack, self.liste)
        self.fenster = _Fenster()
        self.view.window = lambda: self.fenster

    def tearDown(self):
        self.liste.stop()
        for page, alt in zip(self.pe.pages, self._orig_bindung):
            for ex, (st, lbl, fv, ff) in zip(page, alt):
                ex.stack, ex.label, ex.fader_value, ex.fader_function = (
                    st, lbl, fv, ff)
        self.pe.current_page = self._orig_page
        self.state.cue_stacks.clear()
        self.state.cue_stacks.extend(self._orig_stacks)
        self.state.gewaehlte_cueliste = None
        self.view.deleteLater()

    # ── #921: aktuelle Page zuerst ───────────────────────────────────────────

    def test_executor_von_bevorzugt_die_aktuelle_page(self):
        self.pe.get_executor(4, page=0).stack = self.liste
        self.pe.get_executor(2, page=3).stack = self.liste
        self.assertEqual((0, 4), executor_von(self.state, self.liste))
        self.assertEqual((3, 2), executor_von(self.state, self.liste, bevorzugt_page=3))
        self.assertEqual((0, 4), executor_von(self.state, self.liste, bevorzugt_page=5),
                         "ohne Bindung auf der bevorzugten Page: erste in Page-Reihenfolge")

    def test_go_meldet_keine_fremde_page_wenn_die_liste_auch_hier_liegt(self):
        self.pe.get_executor(4, page=0).stack = self.liste    # Page 1, Ex 4
        self.pe.get_executor(2, page=3).stack = self.liste    # Page 4, Ex 2
        self.pe.current_page = 3
        self.view._go()
        self.assertEqual(0, self.liste.current_index, "GO muss laufen")
        self.assertFalse([m for m in self.fenster._leiste.meldungen if "Page" in m],
                         f"Hinweis nennt eine fremde Page: {self.fenster._leiste.meldungen}")
        self.assertNotIn("Page", self.view._lbl_hinweis.text())

    def test_nur_auf_fremder_page_bleibt_der_hinweis(self):
        self.pe.get_executor(4, page=5).stack = self.liste
        self.pe.current_page = 0
        self.view._go()
        self.assertEqual(["„Neue Liste“ liegt auf Page 6, Ex 4"],
                         self.fenster._leiste.meldungen)

    # ── #836: Hinweis veraltet nicht bei Hand-Zuweisung ──────────────────────

    def test_hand_zuweisung_leer_nimmt_den_bindungs_hinweis_weg(self):
        self.view._go()
        self.assertIn("liegt jetzt auf Ex 1", self.view._lbl_hinweis.text())
        ex_widget = self.view._executors_widgets[0]
        ex_widget._combo.setCurrentIndex(0)                    # „— Leer —“
        self.assertIsNone(self.pe.get_executor(1).stack)
        self.assertEqual("", self.view._lbl_hinweis.text(),
                         "Hinweis behauptet weiter eine Bindung, die es nicht mehr gibt")
        self.assertTrue(self.view._lbl_hinweis.isHidden())

    def test_hand_zuweisung_andere_liste_nimmt_den_hinweis_weg(self):
        zweite = self.state.new_cue_stack("Zweite")
        self.view._combo_stack.setCurrentIndex(0)
        self.view._go()
        self.assertTrue(self.view._lbl_hinweis.text())
        ex_widget = self.view._executors_widgets[0]
        ex_widget.refresh_from_state()
        idx = ex_widget._combo.findData(zweite)
        self.assertGreater(idx, 0)
        ex_widget._combo.setCurrentIndex(idx)
        self.assertIs(zweite, self.pe.get_executor(1).stack)
        self.assertEqual("", self.view._lbl_hinweis.text())


if __name__ == "__main__":
    unittest.main()
