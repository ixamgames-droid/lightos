"""UI-139 (Klick-Test 16.11.2026): Show-Manager.

* Fund 3: im Touch-Modus ragten „|<<“, „Play“ und „Stop“ zur Haelfte unter
  die Befehlszeile — die Transportleiste war fest 38 px hoch, die Knoepfe
  mit dem Touch-Stylesheet 48 px. Jetzt: Leiste so hoch wie ihre Knoepfe,
  Knoepfe im Touch >= 44 px; mit der Maus bleibt die Leiste 38 px.
* Fund 12: die Auswahl zeigte eine Show, die Zeitleiste meldete „Keine
  Timeline-Show ausgewaehlt“ — ``_refresh_ui`` fuellte die Auswahl bei
  blockierten Signalen, ohne die Show zu laden. Jetzt laedt sie die Show,
  die in der Auswahl steht.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

import _ui139_masse as m                                             # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402
from src.core.engine.function import FunctionType                    # noqa: E402
from src.core.engine.function_manager import get_function_manager    # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(_app)


def _shows_weg():
    fm = get_function_manager()
    for s in list(fm.by_type(FunctionType.Show)):
        fm.remove(s.id)


class _Basis(unittest.TestCase):
    def setUp(self):
        _shows_weg()
        self.addCleanup(_shows_weg)

    def _ansicht(self, touch, groesse):
        m.touch_setzen(self, touch)
        from src.ui.views.show_manager_view import ShowManagerView
        r = m.Rahmen(touch, groesse)
        v = r.zeige(ShowManagerView())
        v._ui_timer.stop()          # Test ruft _refresh_ui selbst
        return r, v


class TransportleisteTest(_Basis):
    def _knoepfe(self, v):
        return (v._btn_rewind, v._btn_play, v._btn_stop_transport)

    def test_touch_knoepfe_ganz_in_der_leiste(self):
        for name, groesse in m.KLEIN.items():
            r, v = self._ansicht(True, groesse)
            leiste = v._btn_play.parentWidget()
            for b in self._knoepfe(v):
                with self.subTest(aufl=name, knopf=b.text()):
                    self.assertGreaterEqual(b.height(), 44)
                    self.assertTrue(m.sichtbar_in(b, leiste),
                                    f"{b.geometry()} ragt aus der Leiste ({leiste.height()} px)")
                    self.assertTrue(m.sichtbar_in(b, v), "Knopf ragt aus der Ansicht")
                    self.assertTrue(m.text_passt(b), b.text())
            r.close()

    def test_maus_bleibt_kompakt(self):
        r, v = self._ansicht(False, m.KLEIN["1366x768"])
        leiste = v._btn_play.parentWidget()
        self.assertEqual(leiste.height(), 38)
        for b in self._knoepfe(v):
            self.assertTrue(m.sichtbar_in(b, leiste))
            self.assertTrue(m.text_passt(b), b.text())

    def test_fingertipp_auf_play_startet(self):
        r, v = self._ansicht(True, m.KLEIN["1280x800"])
        fm = get_function_manager()
        v._load_show(fm.new_show("UI139 Tipp"))
        b = v._btn_play
        # unteres Viertel des Knopfs — dort lag frueher die Befehlszeile
        p = b.mapTo(r, QPoint(b.width() // 2, b.height() * 3 // 4))
        QTest.touchEvent(r, _DEV).press(0, p, r).commit()
        QTest.touchEvent(r, _DEV).release(0, p, r).commit()
        QApplication.processEvents()
        self.assertTrue(v._playing)
        v._stop()


class AuswahlUndZeitleisteTest(_Basis):
    def test_spaeter_geladene_show_wird_auch_geladen(self):
        r, v = self._ansicht(False, m.KLEIN["1366x768"])
        self.assertIsNone(v._current_show)
        show = get_function_manager().new_show("UI139 Spaeter")   # z. B. Show-Datei geladen
        v._refresh_ui()
        self.assertEqual(v._show_combo.currentData(), show.id)
        self.assertIs(v._current_show, show,
                      "Auswahl zeigt eine Show, die Zeitleiste hat keine")

    def test_geloeschte_show_raeumt_die_zeitleiste(self):
        r, v = self._ansicht(False, m.KLEIN["1366x768"])
        fm = get_function_manager()
        a = fm.new_show("UI139 A")
        v._refresh_ui()
        self.assertIs(v._current_show, a)
        fm.remove(a.id)
        b = fm.new_show("UI139 B")        # gleiche Anzahl, andere Show
        v._refresh_ui()
        self.assertEqual(v._show_combo.currentData(), b.id)
        self.assertIs(v._current_show, b)
        fm.remove(b.id)
        v._refresh_ui()
        self.assertEqual(v._show_combo.count(), 0)
        self.assertIsNone(v._current_show)

    def test_andere_show_datei_mit_gleicher_id(self):
        """Nachbesserung nach Pruefung: Show-Dateien behalten ihre IDs beim
        Laden (from_dict + bump_next_id). Eine andere Datei, deren Show
        dieselbe ID hat, darf nicht die alte Show in der Zeitleiste und den
        alten Namen in der Auswahl stehen lassen."""
        from src.core.engine.show_engine import Show
        r, v = self._ansicht(False, m.KLEIN["1366x768"])
        fm = get_function_manager()
        alt = fm.new_show("UI139 Alte Datei")
        v._refresh_ui()
        self.assertIs(v._current_show, alt)
        neu = Show("UI139 Neue Datei")
        neu.id = alt.id
        fm._functions[alt.id] = neu          # wie from_dict: gleiche ID
        v._refresh_ui()
        self.assertIs(v._current_show, neu, "Zeitleiste zeigt die alte Show")
        self.assertEqual(v._show_combo.currentText(), "UI139 Neue Datei")

    def test_gewaehlte_show_bleibt_gewaehlt(self):
        r, v = self._ansicht(False, m.KLEIN["1366x768"])
        fm = get_function_manager()
        fm.new_show("UI139 Eins")
        zwei = fm.new_show("UI139 Zwei")
        v._refresh_ui()
        v._show_combo.setCurrentIndex(v._show_combo.findData(zwei.id))
        self.assertIs(v._current_show, zwei)
        fm.new_show("UI139 Drei")
        v._refresh_ui()
        self.assertIs(v._current_show, zwei)
        self.assertEqual(v._show_combo.currentData(), zwei.id)


if __name__ == "__main__":
    unittest.main()
