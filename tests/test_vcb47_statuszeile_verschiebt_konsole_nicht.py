"""VCB-47: Statusanzeigen verschieben die Bedienflaeche der Virtual Console nicht.

Befund (Sichtprobe am echten Bildschirm): die Zeile „Aktiver Effekt: …" ueber der
Konsole wurde nur eingeblendet, solange ein Effekt lief. Der erste Tastendruck
schob damit alle Tasten um 22 px nach unten — ein zweiter Tipp an derselben
Bildschirmstelle (Doppeltipp auf eine Flash-/Toggle-Taste) ging daneben oder traf
die Nachbartaste.

Grundsatz, den diese Datei bewacht: im Bedienmodus aendert KEINE Statusanzeige
die Lage der Konsole. Die Zeile hat einen festen Platz („Kein Effekt aktiv", wenn
nichts laeuft), und die Umschaltknoepfe der Werkzeugleiste behalten ihre Breite,
damit die umbrechende Leiste in schmalen Fenstern nicht ploetzlich eine Zeile
mehr oder weniger braucht.

Es wird nichts gesendet (kein Ausgang eingerichtet, kein Ausgabe-Thread).
"""
from __future__ import annotations

import inspect
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from src.core.app_state import get_state                             # noqa: E402
from src.ui.views import virtual_console_view as vcv                 # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton   # noqa: E402
from src.ui.virtualconsole.vc_slider import VCSlider                 # noqa: E402
from src.ui.virtualconsole.vc_widget import VCWidget                 # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


class _MitAnsicht(unittest.TestCase):
    BREITE, HOEHE = 1400, 800

    def setUp(self):
        self.app = _app()
        self.fm = get_state().function_manager
        self.fm.stop_all()
        self.fn = self.fm.new_efx("VCB47-Effekt")
        self._lock_vorher = VCWidget.input_locked
        self._pickup_vorher = VCSlider.soft_takeover
        self.view = vcv.VirtualConsoleView()
        # Der 400-ms-Takt wird hier von Hand ausgeloest, nicht per Uhr.
        self.view._active_fx_timer.stop()
        self.view.resize(self.BREITE, self.HOEHE)
        self.view.show()
        self.view._active_fx_timer.stop()          # showEvent weckt ihn wieder
        self.taste = self.view._canvas._add_widget("VCButton", QPoint(120, 80))
        self.assertIsInstance(self.taste, VCButton)
        self.taste.action = ButtonAction.FUNCTION_TOGGLE
        self.taste.function_id = self.fn.id
        self._takt()

    def tearDown(self):
        self.fm.stop(self.fn.id)
        self.fm.remove(self.fn.id)
        VCWidget.input_locked = self._lock_vorher
        VCSlider.soft_takeover = self._pickup_vorher
        self.view.close()
        self.view.deleteLater()
        self.app.processEvents()

    def _takt(self):
        """Ein Durchlauf des Statustakts samt Layout-Nachlauf."""
        self.view._update_active_fx()
        self.app.processEvents()
        self.app.processEvents()

    def _lage_taste(self):
        return self.taste.mapTo(self.view, QPoint(0, 0))

    def _lage_konsole(self):
        """Lage und Groesse des Konsolen-Bereichs im Fenster."""
        scroll = self.view._main_scroll
        return (scroll.mapTo(self.view, QPoint(0, 0)), scroll.size(),
                self.view._splitter.geometry())


class TasteBleibtAmPlatzTest(_MitAnsicht):
    def test_taste_liegt_nach_dem_ersten_ausloesen_an_derselben_stelle(self):
        vorher = self._lage_taste()
        mitte = self.taste.mapTo(self.view, self.taste.rect().center())
        self.assertIs(self.view.childAt(mitte), self.taste)

        QTest.mouseClick(self.taste, Qt.MouseButton.LeftButton)
        self.assertTrue(self.fn.is_running, "Der Klick muss den Effekt gestartet haben.")
        self._takt()

        self.assertIn(self.fn.name, self.view._lbl_active_fx.text())
        self.assertEqual(self._lage_taste(), vorher)
        # Der zweite Tipp an DERSELBEN Bildschirmstelle trifft dieselbe Taste.
        self.assertIs(self.view.childAt(mitte), self.taste)

    def test_doppeltipp_an_derselben_stelle_schaltet_ein_und_wieder_aus(self):
        mitte = self.taste.mapTo(self.view, self.taste.rect().center())
        for erwartet in (True, False):
            ziel = self.view.childAt(mitte)
            self.assertIs(ziel, self.taste)
            QTest.mouseClick(ziel, Qt.MouseButton.LeftButton)
            self._takt()
            self.assertEqual(bool(self.fn.is_running), erwartet)

    def test_taste_liegt_nach_dem_stoppen_an_derselben_stelle(self):
        vorher = self._lage_taste()
        self.fm.start(self.fn.id)
        self._takt()
        laufend = self._lage_taste()
        self.fm.stop(self.fn.id)
        self._takt()
        self.assertEqual(laufend, vorher)
        self.assertEqual(self._lage_taste(), vorher)
        self.assertEqual(self.view._lbl_active_fx.text(), self.view._TEXT_KEIN_EFFEKT)

    def test_auch_stop_all_verschiebt_nichts(self):
        vorher = self._lage_konsole()
        self.fm.start(self.fn.id)
        self._takt()
        self.fm.stop_all()
        self._takt()
        self.assertEqual(self._lage_konsole(), vorher)


class StatuszeileHatFestenPlatzTest(_MitAnsicht):
    def test_konsolenbereich_ist_mit_und_ohne_effekt_gleich(self):
        ohne = self._lage_konsole()
        self.fm.start(self.fn.id)
        self._takt()
        mit = self._lage_konsole()
        self.fm.stop(self.fn.id)
        self._takt()
        self.assertEqual(mit, ohne)
        self.assertEqual(self._lage_konsole(), ohne)

    def test_zeile_ist_immer_sichtbar_und_gleich_hoch(self):
        lbl = self.view._lbl_active_fx
        hoehen = []
        for laeuft in (False, True, False):
            if laeuft:
                self.fm.start(self.fn.id)
            else:
                self.fm.stop(self.fn.id)
            self._takt()
            self.assertTrue(lbl.isVisible(), "Die Zeile darf nie ausgeblendet werden.")
            self.assertTrue(lbl.text().strip(), "Die Zeile zeigt immer einen Text.")
            hoehen.append((lbl.height(), lbl.geometry().top()))
        self.assertEqual(len(set(hoehen)), 1, hoehen)
        self.assertEqual(lbl.height(), self.view._ZEILE_AKTIVER_EFFEKT_H)

    def test_platzhalter_ist_ein_deutscher_satz_ohne_strich(self):
        self.assertEqual(self.view._lbl_active_fx.text(), "Kein Effekt aktiv")

    def test_langer_effektname_macht_die_ansicht_nicht_breiter(self):
        vorher = self.view.minimumSizeHint().width()
        self.fn.name = "Sehr langer Effektname " * 30
        self.fm.start(self.fn.id)
        self._takt()
        self.assertEqual(self.view.minimumSizeHint().width(), vorher)
        self.assertEqual(self.view.width(), self.BREITE)

    def test_quelltext_blendet_die_zeile_nirgends_aus(self):
        """Waechter gegen den Rueckfall: wer die Zeile wieder „nur bei Bedarf"
        zeigen will, muss an diesem Test vorbei."""
        quelle = inspect.getsource(vcv)
        for verboten in ("_lbl_active_fx.setVisible", "_lbl_active_fx.hide",
                         "_lbl_active_fx.show", "_lbl_active_fx.setHidden"):
            self.assertNotIn(verboten, quelle)


class WerkzeugleisteBleibtGleichHochTest(_MitAnsicht):
    """Die Leiste bricht um (FlowLayout). Aendert ein Umschaltknopf beim Druecken
    seine Breite, braucht sie in schmalen Fenstern ploetzlich eine Zeile mehr —
    und die Konsole rutscht genauso wie durch die Statuszeile."""

    def test_umschaltknoepfe_aendern_ihre_breite_nicht(self):
        v = self.view
        for knopf in (v._btn_pickup, v._btn_touch_lock, v._btn_sidebar):
            vorher = knopf.width()
            knopf.setChecked(True)
            self.app.processEvents()
            self.assertEqual(knopf.width(), vorher, knopf.text())
            knopf.setChecked(False)
            self.app.processEvents()
            self.assertEqual(knopf.width(), vorher, knopf.text())
        # APC LEDs: nur die Darstellung „gedrueckt" pruefen, ohne MIDI anzufassen.
        apc = v._btn_apc_leds
        vorher = apc.width()
        apc.blockSignals(True)
        try:
            apc.setChecked(True)
            self.app.processEvents()
            self.assertEqual(apc.width(), vorher)
            apc.setChecked(False)
        finally:
            apc.blockSignals(False)

    def test_umschalten_verschiebt_die_konsole_in_keiner_fensterbreite(self):
        """Ueber viele Breiten, also auch genau an den Umbruchkanten der Leiste."""
        v = self.view
        for breite in range(520, 1500, 12):
            v.resize(breite, self.HOEHE)
            self.app.processEvents()
            self.app.processEvents()
            oben = v._splitter.geometry().top()
            lage = self._lage_taste().y()
            for knopf in (v._btn_pickup, v._btn_touch_lock, v._btn_midi_learn):
                knopf.setChecked(True)
                self.app.processEvents()
                self.app.processEvents()
                self.assertEqual(
                    v._splitter.geometry().top(), oben,
                    f"Breite {breite}: „{knopf.text()}“ gedrückt verschiebt die Konsole.")
                knopf.setChecked(False)
                self.app.processEvents()
                self.app.processEvents()
                self.assertEqual(v._splitter.geometry().top(), oben, f"Breite {breite}")
            self.assertEqual(self._lage_taste().y(), lage)


if __name__ == "__main__":
    unittest.main()
