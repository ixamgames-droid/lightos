"""UI-147: Befunde aus dem Live-Klicktest 23.11.2026, Bereich Cuelisten/Playback.

1. „Aktive Cue“ blieb nach Show-Wechsel / STOP von aussen (WEB-18) stehen.
2. Nach Show-Laden zeigten Page-Knoepfe/„Page N“ die alte Page.
3. „+ Cue aufnehmen“ mit belegter Nummer legte eine zweite gleiche Nummer an.
4. Befehlszeile: 'at' statt '@' setzte still keinen Wert.
5. Fade-Zellen: '1,5' still verworfen, '-3' angenommen.
6. Cue loeschen ohne Rueckfrage und ohne Rueckgaengig.
7.–9. Handgriffe: Label-Abbrechen bricht ab, Fader-Fuellung unten, GO auf
   leere Liste belegt keinen Executor, Zeiten einheitlich '3.0s'.

Echter AppState + echte PlaybackView (offscreen), Dialoge ersetzt."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from src.core.app_state import get_state
from src.core.engine.cue import Cue
from src.core.undo import get_undo_stack
from src.core.cmdline.parser import parse, SetValueCommand
from src.ui.views import playback_view as pv_mod
from src.ui.views.playback_view import PlaybackView

_app = QApplication.instance() or QApplication([])


def _warte(bedingung, schritte=200):
    for _ in range(schritte):
        if bedingung():
            return True
        _app.processEvents()
    return bedingung()


class _Basis(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.pe = self.state.playback_engine
        self._orig_stacks = list(self.state.cue_stacks)
        self._orig_page = self.pe.current_page
        self._orig_bindung = [[(ex.stack, ex.label, ex.fader_value,
                                ex.fader_function) for ex in page]
                              for page in self.pe.pages]
        self._orig_prog = dict(self.state.programmer)
        self.state.cue_stacks.clear()
        self.state.gewaehlte_cueliste = None
        self.pe.current_page = 0
        for page in self.pe.pages:
            for ex in page:
                ex.stack = None
                ex.label = f"Exec {ex.slot}"
                ex.fader_value = 1.0
                ex.fader_function = "volume"
        get_undo_stack().clear()
        self.liste = self.state.new_cue_stack("Liste A")
        for nr, label in ((1.0, "Voll"), (2.0, "Gedimmt"), (3.0, "Aus")):
            self.liste.add_cue(Cue(number=nr, label=label, fade_in=0.0,
                                   values={1: {"intensity": 100}}))
        self.view = PlaybackView()
        self.view._combo_stack.setCurrentIndex(0)
        self.assertIs(self.view._current_stack, self.liste)
        self.view.window = lambda: self.view   # keine Statuszeile noetig

    def tearDown(self):
        for st in self.state.cue_stacks:
            st.stop()
        for page, alt in zip(self.pe.pages, self._orig_bindung):
            for ex, (st, lbl, fv, ff) in zip(page, alt):
                ex.stack, ex.label, ex.fader_value, ex.fader_function = (
                    st, lbl, fv, ff)
        self.pe.current_page = self._orig_page
        self.state.cue_stacks.clear()
        self.state.cue_stacks.extend(self._orig_stacks)
        self.state.gewaehlte_cueliste = None
        self.state.programmer.clear()
        self.state.programmer.update(self._orig_prog)
        get_undo_stack().clear()
        self.view.deleteLater()
        _app.processEvents()


class AktiveCueAnzeigeTest(_Basis):
    """Punkt 1 + WEB-18."""

    def _laufen_bis_cue_2(self):
        self.view._go()
        self.view._go()
        self.view._update_cue_highlight()
        self.assertIn("Cue 2.0", self.view._lbl_current.text())

    def test_stop_von_aussen_leert_anzeige(self):
        self._laufen_bis_cue_2()
        self.liste.stop()                 # wie STOP ueber Web/OSC
        self.view._update_cue_highlight()
        self.assertEqual(self.view._lbl_current.text(), "—")
        self.assertEqual(self.view._lbl_next.text(), "Nächste: —")

    def test_show_wechsel_leert_anzeige(self):
        self._laufen_bis_cue_2()
        # neue Show: andere (leere) Cueliste, alte weg
        self.state.cue_stacks.clear()
        neu = self.state.new_cue_stack("Neue Show")
        self.view._sync_refresh()
        self.assertIs(self.view._current_stack, neu)
        self.view._update_cue_highlight()
        self.assertEqual(self.view._lbl_current.text(), "—")
        self.assertNotIn("Gedimmt", self.view._lbl_next.text())

    def test_ganz_ohne_cueliste_leer(self):
        self._laufen_bis_cue_2()
        self.state.cue_stacks.clear()
        self.view._sync_refresh()
        self.assertIsNone(self.view._current_stack)
        self.view._update_cue_highlight()
        self.assertEqual(self.view._lbl_current.text(), "—")


class PageNachShowLadenTest(_Basis):
    """Punkt 2."""

    def test_from_dict_meldet_page_wechsel(self):
        gemeldet = []
        cb = gemeldet.append
        self.pe.subscribe_page(cb)
        try:
            self.pe.set_page(5)
            gemeldet.clear()
            # Alt-Show ohne current_page (wie gespeichert) -> Page 1
            self.pe.from_dict({"pages": []}, self.state.cue_stacks)
            self.assertEqual(self.pe.current_page, 0)
            self.assertEqual(gemeldet, [0])
            # gleiche Page -> keine Meldung
            gemeldet.clear()
            self.pe.from_dict({}, self.state.cue_stacks)
            self.assertEqual(gemeldet, [])
        finally:
            self.pe.unsubscribe_page(cb)

    def test_page_knoepfe_folgen_show_laden(self):
        self.view._switch_page(5)
        self.assertTrue(self.view._page_buttons[5].isChecked())
        self.pe.from_dict({}, self.state.cue_stacks)
        self.assertTrue(_warte(lambda: self.view._page_buttons[0].isChecked()))
        self.assertFalse(self.view._page_buttons[5].isChecked())

    def test_sync_refresh_gleicht_knoepfe_an(self):
        self.view._switch_page(5)
        self.pe.current_page = 0           # still gesetzt (ohne Meldung)
        self.view._sync_refresh()
        self.assertTrue(self.view._page_buttons[0].isChecked())
        self.assertFalse(self.view._page_buttons[5].isChecked())


class DoppelteNummerTest(_Basis):
    """Punkt 3 (+ Punkt 7: Label-Abbrechen)."""

    def setUp(self):
        super().setUp()
        self._orig_double = QInputDialog.getDouble
        self._orig_text = QInputDialog.getText
        self.state.programmer.clear()
        self.state.programmer[7] = {"intensity": 42}

    def tearDown(self):
        QInputDialog.getDouble = self._orig_double
        QInputDialog.getText = self._orig_text
        super().tearDown()

    def _eingabe(self, nummer, label="Neu", label_ok=True):
        QInputDialog.getDouble = staticmethod(lambda *a, **k: (nummer, True))
        QInputDialog.getText = staticmethod(lambda *a, **k: (label, label_ok))

    def _nummern(self):
        return [c.number for c in self.liste.cues]

    def test_naechste_freie_nummer(self):
        f = pv_mod.naechste_freie_cue_nummer
        self.assertEqual(f(self.liste, 4.0), 4.0)
        self.assertEqual(f(self.liste, 1.0), 1.1)
        self.liste.add_cue(Cue(number=1.1))
        self.assertEqual(f(self.liste, 1.0), 1.2)

    def test_einfuegen_vergibt_freie_nummer(self):
        self._eingabe(1.0)
        self.view._frage_doppelte_nummer = lambda n: "einfuegen"
        self.view._record_cue()
        self.assertEqual(self._nummern(), [1.0, 1.1, 2.0, 3.0])

    def test_abbrechen_nimmt_nichts_auf(self):
        self._eingabe(2.0)
        self.view._frage_doppelte_nummer = lambda n: None
        self.view._record_cue()
        self.assertEqual(self._nummern(), [1.0, 2.0, 3.0])

    def test_ersetzen_behaelt_zeiten_und_ist_rueckgaengig(self):
        alt = self.liste.cues[1]
        alt.fade_in = 4.5
        self._eingabe(2.0, label="Ersetzt")
        self.view._frage_doppelte_nummer = lambda n: "ersetzen"
        self.view._record_cue()
        self.assertEqual(self._nummern(), [1.0, 2.0, 3.0])
        c2 = self.liste.cues[1]
        self.assertEqual(c2.values, {7: {"intensity": 42}})
        self.assertEqual(c2.label, "Ersetzt")
        self.assertEqual(c2.fade_in, 4.5)
        self.assertTrue(get_undo_stack().undo())
        self.assertIs(self.liste.cues[1], alt)
        self.assertEqual(alt.values, {1: {"intensity": 100}})

    def test_rueckfrage_voreinstellung_abbrechen(self):
        gesehen = {}

        def schliessen():
            box = QApplication.activeModalWidget()
            gesehen["box"] = box
            if isinstance(box, QMessageBox):
                gesehen["default"] = box.defaultButton().text()
                gesehen["knoepfe"] = [b.text() for b in box.buttons()]
                box.reject()                 # wie Esc

        QTimer.singleShot(0, schliessen)
        self.assertIsNone(self.view._frage_doppelte_nummer(1.0))
        self.assertIsInstance(gesehen.get("box"), QMessageBox)
        self.assertTrue(any("ersetzen" in t for t in gesehen["knoepfe"]))
        self.assertTrue(any("1.1" in t for t in gesehen["knoepfe"]))
        self.assertNotIn("ersetzen", gesehen["default"])

    def test_rueckfrage_touch_44px(self):
        gesehen = {}
        orig = pv_mod.touch_aktiv
        pv_mod.touch_aktiv = lambda: True

        def schliessen():
            box = QApplication.activeModalWidget()
            gesehen["h"] = [b.minimumHeight() for b in box.buttons()]
            box.reject()

        try:
            QTimer.singleShot(0, schliessen)
            self.view._frage_doppelte_nummer(1.0)
        finally:
            pv_mod.touch_aktiv = orig
        self.assertTrue(gesehen["h"])
        self.assertTrue(all(h >= 44 for h in gesehen["h"]), gesehen)

    def test_label_abbrechen_bricht_ab(self):
        self._eingabe(5.0, label="", label_ok=False)
        self.view._record_cue()
        self.assertEqual(self._nummern(), [1.0, 2.0, 3.0])

    def test_leeres_label_wird_cue_n(self):
        self._eingabe(5.0, label="  ")
        self.view._record_cue()
        self.assertEqual(self.liste.cues[-1].label, "Cue 5")

    def test_befehlszeile_lehnt_doppelte_nummer_ab(self):
        self.state.gewaehlte_cueliste = self.liste
        res = parse("record cue 2").execute(self.state)
        self.assertFalse(res.ok)
        self.assertIn("gibt es", res.message)
        self.assertEqual(self._nummern(), [1.0, 2.0, 3.0])
        res = parse("record cue 4").execute(self.state)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(self._nummern(), [1.0, 2.0, 3.0, 4.0])


class BefehlszeileAtTest(unittest.TestCase):
    """Punkt 4."""

    def test_at_wie_klammeraffe(self):
        for text in ("1 thru 5 at 80", "1 THRU 5 AT 80"):
            cmd = parse(text)
            self.assertIsInstance(cmd, SetValueCommand, text)
            self.assertEqual(cmd.value_pct, 80)
            self.assertEqual(cmd.selection.ranges, [(1, 5)])

    def test_at_full_und_einzeln(self):
        self.assertEqual(parse("2 at 50").value_pct, 50)
        self.assertEqual(parse("all at full").value_pct, 100)
        self.assertEqual(parse("3 at off").value_pct, 0)


class FadeZellenTest(_Basis):
    """Punkt 5 (+ Punkt 9: einheitliches Format)."""

    def _zelle(self, row, col, text):
        self.view._table.item(row, col).setText(text)   # loest itemChanged aus
        return self.view._table.item(row, col).text()

    def test_lies_zeit(self):
        f = pv_mod.lies_zeit
        u = pv_mod._UNGUELTIG
        self.assertEqual(f("1,5"), 1.5)
        self.assertEqual(f("1.5s"), 1.5)
        self.assertEqual(f(" 3 "), 3.0)
        self.assertIs(f("-3"), u)
        self.assertIs(f("abc"), u)
        self.assertIs(f("inf"), u)
        self.assertIs(f("nan"), u)
        self.assertIs(f("—"), u)
        self.assertIsNone(f("—", leer_erlaubt=True))
        self.assertEqual(f("0,25", leer_erlaubt=True), 0.25)

    def test_komma_wird_uebernommen(self):
        txt = self._zelle(0, 2, "1,5")
        self.assertEqual(self.liste.cues[0].fade_in, 1.5)
        self.assertEqual(txt, "1.5s")

    def test_negativ_und_text_abgelehnt(self):
        self.liste.cues[0].fade_out = 2.0
        self.view._refresh_table()
        txt = self._zelle(0, 3, "-3")
        self.assertEqual(self.liste.cues[0].fade_out, 2.0)
        self.assertEqual(txt, "2.0s")
        txt = self._zelle(0, 4, "abc")
        self.assertEqual(self.liste.cues[0].delay_in, 0.0)
        self.assertEqual(txt, "0.0s")
        self.assertIn("keine gültige Zeit", self.view._lbl_hinweis.text())

    def test_ganze_zahl_einheitlich(self):
        self.assertEqual(self._zelle(1, 2, "3"), "3.0s")

    def test_follow_aus_und_an(self):
        self.assertEqual(self._zelle(0, 5, "1,2"), "1.2s")
        self.assertEqual(self.liste.cues[0].follow, 1.2)
        self.assertEqual(self._zelle(0, 5, "—"), "—")
        self.assertIsNone(self.liste.cues[0].follow)
        self.assertEqual(self._zelle(0, 5, "-2"), "—")
        self.assertIsNone(self.liste.cues[0].follow)


class CueLoeschenTest(_Basis):
    """Punkt 6."""

    def _markiere(self, row):
        self.view._table.clearSelection()
        self.view._table.selectRow(row)

    def test_nein_loescht_nicht(self):
        self._markiere(1)
        self.view._frage_cue_loeschen = lambda cues: False
        self.view._delete_cue()
        self.assertEqual(len(self.liste.cues), 3)

    def test_ja_loescht_und_rueckgaengig_holt_zurueck(self):
        self._markiere(1)
        c2 = self.liste.cues[1]
        self.view._frage_cue_loeschen = lambda cues: True
        self.view._delete_cue()
        self.assertEqual([c.number for c in self.liste.cues], [1.0, 3.0])
        us = get_undo_stack()
        self.assertTrue(us.can_undo())
        self.assertTrue(us.undo())
        self.assertEqual([c.number for c in self.liste.cues], [1.0, 2.0, 3.0])
        self.assertIs(self.liste.cues[1], c2)
        self.assertTrue(_warte(lambda: self.view._table.rowCount() == 3))
        self.assertTrue(us.redo())
        self.assertEqual([c.number for c in self.liste.cues], [1.0, 3.0])

    def test_rueckfrage_voreinstellung_nein(self):
        gesehen = {}
        orig = QMessageBox.question

        def frage(*a, **k):
            gesehen["args"] = a
            return QMessageBox.StandardButton.No

        QMessageBox.question = staticmethod(frage)
        try:
            self.assertFalse(self.view._frage_cue_loeschen([self.liste.cues[0]]))
        finally:
            QMessageBox.question = orig
        self.assertEqual(gesehen["args"][-1], QMessageBox.StandardButton.No)
        self.assertIn("Cue 1", gesehen["args"][2])


class HandgriffeTest(_Basis):
    """Punkte 8 und 9."""

    def test_go_auf_leere_liste_belegt_keinen_executor(self):
        leer = self.state.new_cue_stack("Leer")
        self.view._current_stack = leer
        self.view._go()
        self.assertFalse(any(ex.stack is leer for page in self.pe.pages
                             for ex in page))
        self.assertIn("keine Cue", self.view._lbl_hinweis.text())

    def test_executor_fader_fuellung_unten(self):
        ss = self.view._executors_widgets[0]._fader.styleSheet()
        self.assertIn("add-page:vertical", ss)
        self.assertIn("#0978FF", ss.split("add-page:vertical", 1)[1])


if __name__ == "__main__":
    unittest.main()
