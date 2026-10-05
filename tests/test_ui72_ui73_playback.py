"""UI-72 / UI-73 — zwei Playback-Befunde aus dem Live-Funktionstest (03.10.2026).

UI-72: „+ Neu“ legte die Cueliste an, waehlte sie aber nicht aus — die folgende
„+ Cue aufnehmen“-Aufnahme landete in der alten Liste.
UI-73: GO auf einer Liste, die auf einer ANDEREN Page liegt, spielte ohne jeden
Hinweis — die Executor-Leiste der aktuellen Page blieb leer.
Echter AppState + echte PlaybackView (offscreen), Aufbau wie test_ui68.
"""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.cue import Cue
from src.ui.main_window import MainWindow
from src.ui.views.playback_view import PlaybackView

_app = QApplication.instance() or QApplication([])


class _Statusleiste:
    def __init__(self):
        self.meldungen = []

    def showMessage(self, text, timeout=0):
        self.meldungen.append(text)


class _FensterAttrappe:
    """Für MainWindow._global_transport (Leertaste) — echter AppState plus
    Statusleiste."""
    _global_transport = getattr(MainWindow, "_global_transport", None)

    def __init__(self, state):
        self._state = state
        self._leiste = _Statusleiste()

    def statusBar(self):
        return self._leiste


class _Basis(unittest.TestCase):
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
        for nr, wert in ((1.0, 128), (2.0, 76)):
            self.liste.add_cue(Cue(number=nr, fade_in=0.0,
                                   values={1: {"intensity": wert}}))
        self.view = PlaybackView()
        self.view._combo_stack.setCurrentIndex(0)
        self.assertIs(self.view._current_stack, self.liste)
        self._leiste = _Statusleiste()
        fenster = _FensterAttrappe(self.state)
        fenster._leiste = self._leiste
        self.view.window = lambda: fenster

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



class NeueListeWirdGewaehltTest(_Basis):
    """UI-72."""

    def test_neu_waehlt_die_neue_liste(self):
        from unittest import mock
        with mock.patch("src.ui.views.playback_view.QInputDialog.getText",
                        return_value=("Test UI72", True)):
            self.view._new_stack()
        neu = self.state.cue_stacks[-1]
        self.assertEqual(neu.name, "Test UI72")
        self.assertIs(self.view._current_stack, neu, "neue Liste nicht ausgewaehlt")
        self.assertEqual(self.view._combo_stack.currentText(), "Test UI72")
        self.assertIs(self.state.gewaehlte_cueliste, neu,
                      "Aufnahme-Ziel (UI-62) zeigt nicht auf die neue Liste")

    def test_abbrechen_aendert_nichts(self):
        from unittest import mock
        with mock.patch("src.ui.views.playback_view.QInputDialog.getText",
                        return_value=("", False)):
            self.view._new_stack()
        self.assertIs(self.view._current_stack, self.liste)


class ListeAufAndererPageTest(_Basis):
    """UI-73."""

    def test_go_nennt_page_und_executor(self):
        ex = self.pe.get_executor(3, 6)        # Page 7, Ex 3
        ex.stack = self.liste
        self.view._go()
        text = self.view._lbl_hinweis.text()
        self.assertIn("Page 7", text, text)
        self.assertIn("Ex 3", text, text)
        self.assertTrue(any("Page 7" in m for m in self._leiste.meldungen),
                        "Hinweis fehlt in der Statuszeile")
        # nicht doppelt gebunden (UI-68-Regel bleibt)
        self.assertIsNone(self.pe.get_executor(1, 0).stack)

    def test_auf_der_aktuellen_page_kein_hinweis(self):
        self.pe.get_executor(2, 0).stack = self.liste
        self.view._go()
        self.assertEqual(self.view._lbl_hinweis.text(), "")


if __name__ == "__main__":
    unittest.main()
