"""UI-62: „Cue aufnehmen“ (Menü Show / Taste R) und die Kommandozeile
„record cue“ nehmen in die im Playback GEWÄHLTE Cueliste auf — früher fest in
cue_stacks[0]. Rückfall: erste Cueliste (keine Auswahl / Auswahl gelöscht)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.cmdline.parser import parse
from src.ui.main_window import MainWindow
from src.ui.views.playback_view import PlaybackView

_app = QApplication.instance() or QApplication([])


class _Statusleiste:
    def __init__(self):
        self.meldungen = []

    def showMessage(self, text, timeout=0):
        self.meldungen.append(text)


class _FensterAttrappe:
    """Nur das, was MainWindow._quick_record_cue braucht — den echten AppState
    plus eine Statusleiste (ein volles MainWindow ist für den Test zu schwer)."""
    def __init__(self, state):
        self._state = state
        self._leiste = _Statusleiste()

    def statusBar(self):
        return self._leiste


class AufnahmeGewaehlteCuelisteTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self._orig_programmer = dict(self.state.programmer)
        self._orig_stacks = list(self.state.cue_stacks)
        self.state.cue_stacks.clear()
        self.state.programmer.clear()
        self.state.gewaehlte_cueliste = None
        self.state.programmer[1] = {"intensity": 255}

    def tearDown(self):
        self.state.cue_stacks.clear()
        self.state.cue_stacks.extend(self._orig_stacks)
        self.state.programmer.clear()
        self.state.programmer.update(self._orig_programmer)
        self.state.gewaehlte_cueliste = None

    def _taste_r(self):
        fenster = _FensterAttrappe(self.state)
        MainWindow._quick_record_cue(fenster)
        return fenster._leiste.meldungen

    def test_taste_r_nimmt_in_playback_auswahl_auf(self):
        a = self.state.new_cue_stack("Akt 1")
        b = self.state.new_cue_stack("Akt 2")
        view = PlaybackView()
        view._on_stack_selected(1)
        self.assertIs(self.state.gewaehlte_cueliste, b)

        meldungen = self._taste_r()
        self.assertEqual(len(a.cues), 0, "Cue landete in der ersten Liste")
        self.assertEqual([c.number for c in b.cues], [1.0])
        self.assertTrue(any("Akt 2" in m for m in meldungen), meldungen)

    def test_auswahl_gilt_auch_ohne_offene_playback_ansicht(self):
        self.state.new_cue_stack("A")
        b = self.state.new_cue_stack("B")
        view = PlaybackView()
        view._on_stack_selected(1)
        view.deleteLater()
        del view
        self._taste_r()
        self.assertEqual(len(b.cues), 1)

    def test_rueckfall_erste_liste_ohne_auswahl(self):
        a = self.state.new_cue_stack("A")
        self.state.new_cue_stack("B")
        self._taste_r()
        self.assertEqual(len(a.cues), 1)

    def test_rueckfall_erste_liste_wenn_auswahl_geloescht(self):
        a = self.state.new_cue_stack("A")
        b = self.state.new_cue_stack("B")
        self.state.gewaehlte_cueliste = b
        self.state.remove_cue_stack(b)
        self.assertIs(self.state.aufnahme_cueliste(), a)
        self._taste_r()
        self.assertEqual(len(a.cues), 1)

    def test_neue_ansicht_uebernimmt_gemerkte_auswahl(self):
        self.state.new_cue_stack("A")
        b = self.state.new_cue_stack("B")
        self.state.gewaehlte_cueliste = b
        view = PlaybackView()
        self.assertIs(view._current_stack, b)
        self.assertEqual(view._combo_stack.currentIndex(), 1)

    def test_kommandozeile_record_cue_nimmt_auswahl(self):
        a = self.state.new_cue_stack("A")
        b = self.state.new_cue_stack("B")
        self.state.gewaehlte_cueliste = b
        res = parse("record cue 3").execute(self.state)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(len(a.cues), 0)
        self.assertEqual([c.number for c in b.cues], [3.0])
        self.assertIn("B", res.message)

    def test_ohne_cueliste_kein_absturz(self):
        self.assertIsNone(self.state.aufnahme_cueliste())


if __name__ == "__main__":
    unittest.main()
