"""UI-68: GO im Playback-Tab auf eine Cueliste OHNE Executor machte „Aktive Cue“,
aber kein Licht — PlaybackEngine.compute_merged tickt nur Executor-Stacks.

Jetzt: GO/Zurück/„Hierhin springen“ legen die Liste auf den ERSTEN FREIEN
Executor der aktuellen Page (nie einen belegten überschreiben) und melden
„liegt jetzt auf Ex N“; ist keiner frei, gibt es kein GO, nur den Hinweis
„Kein freier Executor …“. Die globalen Wege (Leertaste/Kommandozeile/Web/OSC)
binden bewusst NICHT (Begründung im Docstring von src/core/cueliste_ziel.py).
Echter AppState + echte PlaybackView (offscreen)."""
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


class GoOhneExecutorTest(unittest.TestCase):
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

    def _licht(self):
        # Fade-Zeit 0 heisst intern 1 ms — kurz warten, dann ist der Fade fertig.
        time.sleep(0.01)
        return self.pe.compute_merged().get(1, {}).get("intensity", 0)

    def _gebunden(self, slot, page=0):
        return self.pe.get_executor(slot, page).stack

    def test_go_legt_liste_auf_ersten_freien_executor_und_macht_licht(self):
        self.view._go()
        self.assertIs(self._gebunden(1), self.liste)
        self.assertEqual(self.liste.current_index, 0)
        self.assertEqual(self._licht(), 128)
        self.assertTrue(any("liegt jetzt auf Ex 1" in m
                            for m in self._leiste.meldungen), self._leiste.meldungen)
        self.assertIn("Ex 1", self.view._lbl_hinweis.text())
        # Executor-Leiste zeigt die neue Belegung sofort
        self.assertIs(self.view._executors_widgets[0]._combo.currentData(),
                      self.liste)
        # zweites GO: keine weitere Bindung, keine neue Meldung
        n = len(self._leiste.meldungen)
        self.view._go()
        self.assertEqual(self._licht(), 76)
        self.assertEqual(len(self._leiste.meldungen), n)
        self.assertEqual(sum(ex.stack is self.liste for ex in self.pe.pages[0]), 1)

    def test_belegte_executoren_werden_nie_ueberschrieben(self):
        andere = self.state.new_cue_stack("Hauptliste")
        self.pe.get_executor(1).stack = andere
        self.pe.get_executor(2).stack = andere
        self.view._go()
        self.assertIs(self._gebunden(1), andere)
        self.assertIs(self._gebunden(2), andere)
        self.assertIs(self._gebunden(3), self.liste)
        self.assertIn("Ex 3", self.view._lbl_hinweis.text())

    def test_kein_freier_executor_kein_go_nur_hinweis(self):
        andere = self.state.new_cue_stack("Hauptliste")
        for ex in self.pe.pages[0]:
            ex.stack = andere
        self.view._go()
        self.assertEqual(self.liste.current_index, -1)
        self.assertTrue(all(ex.stack is andere for ex in self.pe.pages[0]))
        self.assertTrue(any("Kein freier Executor" in m
                            for m in self._leiste.meldungen), self._leiste.meldungen)
        self.assertIn("Kein freier Executor", self.view._lbl_hinweis.text())

    def test_nur_sichtbare_slots_der_leiste(self):
        # Ex 1–10 belegt, Ex 11–20 frei: Leiste zeigt nur 1–10 -> nicht binden
        andere = self.state.new_cue_stack("Hauptliste")
        for ex in self.pe.pages[0][:10]:
            ex.stack = andere
        self.view._go()
        self.assertEqual(self.liste.current_index, -1)
        self.assertIsNone(self._gebunden(11))

    def test_aktuelle_page_wird_belegt(self):
        self.pe.current_page = 2
        self.view._go()
        self.assertIs(self._gebunden(1, page=2), self.liste)
        self.assertIsNone(self._gebunden(1, page=0))

    def test_liste_auf_anderer_page_wird_nicht_doppelt_gebunden(self):
        self.pe.get_executor(4, page=5).stack = self.liste
        self.view._go()
        self.assertIsNone(self._gebunden(1))
        self.assertEqual(self._licht(), 128)
        # UI-73: kein Binden, aber ein Hinweis, WO die Liste laeuft (vorher
        # stumm — die Executor-Leiste der aktuellen Page blieb leer).
        self.assertEqual(self._leiste.meldungen, ["„Neue Liste“ liegt auf Page 6, Ex 4"])

    def test_back_bindet_stop_nicht(self):
        self.view._stop()
        self.assertIsNone(self._gebunden(1))
        self.view._back()
        self.assertIs(self._gebunden(1), self.liste)

    def test_hierhin_springen_bindet(self):
        self.view._table.selectRow(1)
        self.view._go_to_selected()
        self.assertIs(self._gebunden(1), self.liste)
        self.assertEqual(self._licht(), 76)

    def test_belegung_wird_mit_der_show_gespeichert(self):
        self.view._go()
        daten = self.pe.to_dict(self.state.cue_stacks)
        self.assertIn('"stack_index": 0', str(daten).replace("'", '"'))

    def test_leertaste_bindet_bewusst_nicht(self):
        # Fall d der Transport-Regel: Warnung bleibt, keine stille Bindung.
        fenster = _FensterAttrappe(self.state)
        fenster._global_transport("go", "GO")
        self.assertTrue(all(ex.stack is None for ex in self.pe.pages[0]))
        self.assertTrue(any("kein Licht" in m for m in fenster._leiste.meldungen))

    # ── Fader auf 0 / reservierte Slots ──────────────────────────────────────

    def test_slot_mit_fader_auf_null_wird_uebersprungen(self):
        # Ex 1 leer, aber Fader per MIDI/OSC auf 0 -> GO bindet an Ex 2
        self.pe.get_executor(1).fader_value = 0.0
        self.view._go()
        self.assertIsNone(self._gebunden(1))
        self.assertIs(self._gebunden(2), self.liste)
        self.assertEqual(self._licht(), 128)
        self.assertIn("Ex 2", self.view._lbl_hinweis.text())

    def test_nur_slots_mit_fader_null_kein_go_klarer_hinweis(self):
        for ex in self.pe.pages[0]:
            ex.fader_value = 0.0
        self.view._go()
        self.assertEqual(self.liste.current_index, -1)
        self.assertTrue(all(ex.stack is None for ex in self.pe.pages[0]))
        text = self.view._lbl_hinweis.text()
        self.assertIn("Ex 1", text)
        self.assertIn("Fader auf 0", text)
        self.assertTrue(any("Fader auf 0" in m for m in self._leiste.meldungen),
                        self._leiste.meldungen)

    def test_fader_null_mit_anderer_funktion_bleibt_frei(self):
        # Rate-/Crossfade-Fader auf 0 dimmt nicht -> Slot gilt als frei
        ex = self.pe.get_executor(1)
        ex.fader_function = "rate"
        ex.fader_value = 0.0
        self.view._go()
        self.assertIs(self._gebunden(1), self.liste)

    def test_slot_mit_eigenem_label_wird_nicht_genommen(self):
        self.pe.get_executor(1).label = "Reserviert Strobe"
        self.view._go()
        self.assertIsNone(self._gebunden(1))
        self.assertIs(self._gebunden(2), self.liste)

    # ── Hinweis veraltet nicht ───────────────────────────────────────────────

    def _hinweis_steht(self):
        # Liste von allen Executoren loesen -> naechstes GO bindet neu und meldet
        for page in self.pe.pages:
            for ex in page:
                if ex.stack is self.liste:
                    ex.stack = None
        self.view._go()
        self.assertTrue(self.view._lbl_hinweis.text())

    def test_hinweis_weg_nach_sync_refresh(self):
        self._hinweis_steht()
        self.view._sync_refresh()
        self.assertEqual(self.view._lbl_hinweis.text(), "")
        self.assertTrue(self.view._lbl_hinweis.isHidden())

    def test_hinweis_weg_nach_page_wechsel(self):
        self._hinweis_steht()
        self.view._switch_page(1)
        self.assertEqual(self.view._lbl_hinweis.text(), "")
        self._hinweis_steht()
        self.view._on_page_changed_from_engine(0)
        self.assertEqual(self.view._lbl_hinweis.text(), "")

    def test_hinweis_weg_nach_listen_aenderung(self):
        # Show-Laden und Loeschen melden "stacks_changed"
        self._hinweis_steht()
        self.state.new_cue_stack("Zweite")
        self.assertEqual(self.view._lbl_hinweis.text(), "")
        self._hinweis_steht()
        self.view._on_state("stacks_changed", None)
        self.assertEqual(self.view._lbl_hinweis.text(), "")


if __name__ == "__main__":
    unittest.main()
