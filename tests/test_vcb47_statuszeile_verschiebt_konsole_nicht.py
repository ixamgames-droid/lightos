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
from PySide6.QtGui import QFont                                      # noqa: E402
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


class SchwierigeEffektnamenTest(_MitAnsicht):
    """Gegenpruefung: Namen, die eine Zeile hoeher machen koennten (Zeilenumbruch,
    HTML-Markup, sehr lang), und mehrere gleichzeitig laufende Effekte."""

    NAMEN = (
        "Sehr langer Effektname " * 40,
        "Zeile 1\nZeile 2\nZeile 3",
        "<h1>Gross</h1><br><br><table><tr><td>a</td></tr><tr><td>b</td></tr></table>",
    )

    def test_kein_name_veraendert_hoehe_oder_lage(self):
        vorher = (self._lage_taste(), self._lage_konsole())
        for name in self.NAMEN:
            self.fn.name = name
            self.fm.start(self.fn.id)
            self._takt()
            lbl = self.view._lbl_active_fx
            self.assertIn("Aktiver Effekt", lbl.text())
            self.assertEqual(lbl.height(), self.view._ZEILE_AKTIVER_EFFEKT_H, name[:20])
            self.assertEqual((self._lage_taste(), self._lage_konsole()), vorher, name[:20])
            self.fm.stop(self.fn.id)
            self._takt()
            self.assertEqual((self._lage_taste(), self._lage_konsole()), vorher, name[:20])

    def test_name_wird_als_reiner_text_in_einer_zeile_gezeigt(self):
        """Ein Effektname ist kein Markup: „<h1>…“ darf nicht als Ueberschrift
        gesetzt werden, und ein Zeilenumbruch im Namen darf die (22 px hohe)
        Zeile nicht auf ihre mittlere Textzeile verkuerzen."""
        lbl = self.view._lbl_active_fx
        self.assertEqual(lbl.textFormat(), Qt.TextFormat.PlainText)
        self.assertFalse(lbl.wordWrap())
        self.fn.name = "Zeile 1\nZeile 2\tZeile 3"
        self.fm.start(self.fn.id)
        self._takt()
        self.assertNotIn("\n", lbl.text())
        self.assertNotIn("\t", lbl.text())
        self.assertIn("Zeile 1 Zeile 2 Zeile 3", lbl.text())

    def test_mehrere_effekte_nacheinander_verschieben_nichts(self):
        weitere = [self.fm.new_efx(f"VCB47-weiterer-{i}") for i in range(3)]
        try:
            vorher = (self._lage_taste(), self._lage_konsole())
            for fn in [self.fn] + weitere:
                self.fm.start(fn.id)
                self._takt()
                self.assertEqual((self._lage_taste(), self._lage_konsole()), vorher)
            self.assertIn("(+3 weitere)", self.view._lbl_active_fx.text())
            for fn in weitere + [self.fn]:
                self.fm.stop(fn.id)
                self._takt()
                self.assertEqual((self._lage_taste(), self._lage_konsole()), vorher)
            self.assertEqual(self.view._lbl_active_fx.text(), self.view._TEXT_KEIN_EFFEKT)
        finally:
            for fn in weitere:
                self.fm.stop(fn.id)
                self.fm.remove(fn.id)


class WechselUndFensterTest(_MitAnsicht):
    """Gegenpruefung: Wechsel Bearbeiten/Bedienen, Bank-Wechsel, Bibliothek,
    Popout und Zurueckholen, groessere Programmschrift — jeweils mit laufendem
    Effekt, in vielen Fensterbreiten."""

    # Unterhalb davon waechst das freistehende Testfenster im Bearbeiten-Modus
    # von selbst (Mindestbreite der Bearbeiten-Leiste); das Hauptfenster ist
    # ohnehin mindestens 900 px breit.
    BREITEN = range(540, 1500, 16)

    def _oben(self):
        return (self.view._splitter.geometry().top(), self._lage_taste())

    def test_bearbeiten_und_zurueck_landet_an_derselben_stelle(self):
        v = self.view
        for breite in self.BREITEN:
            v.resize(breite, self.HOEHE)
            self.app.processEvents()
            self.app.processEvents()
            vorher = self._oben()
            v._btn_edit.setChecked(True)
            self.app.processEvents()
            self.fm.start(self.fn.id)
            self._takt()
            v._btn_edit.setChecked(False)
            self.app.processEvents()
            self._takt()
            self.assertEqual(self._oben(), vorher, f"Breite {breite}")
            self.fm.stop(self.fn.id)
            self._takt()
            self.assertEqual(self._oben(), vorher, f"Breite {breite}")

    def test_effekt_start_und_stopp_in_jeder_fensterbreite(self):
        v = self.view
        for breite in range(280, 1500, 9):
            v.resize(breite, self.HOEHE)
            self.app.processEvents()
            self.app.processEvents()
            vorher = self._oben()
            self.fm.start(self.fn.id)
            self._takt()
            self.assertEqual(self._oben(), vorher, f"Breite {breite}")
            self.fm.stop(self.fn.id)
            self._takt()
            self.assertEqual(self._oben(), vorher, f"Breite {breite}")

    def test_bank_wechsel_und_bibliothek_verschieben_die_konsole_nicht(self):
        v = self.view
        for breite in self.BREITEN:
            v.resize(breite, self.HOEHE)
            self.app.processEvents()
            self.app.processEvents()
            oben = v._splitter.geometry().top()
            links = v._main_scroll.mapTo(v, QPoint(0, 0))
            for bank in (9, 0):
                v._canvas.set_active_bank(bank)
                self.app.processEvents()
                self.assertEqual(v._splitter.geometry().top(), oben, f"Breite {breite}")
            for sichtbar in (False, True):
                v._btn_sidebar.setChecked(sichtbar)
                self.app.processEvents()
                self.app.processEvents()
                self.assertEqual(v._splitter.geometry().top(), oben, f"Breite {breite}")
                self.assertEqual(v._main_scroll.mapTo(v, QPoint(0, 0)), links)
        self.assertEqual(v._lbl_bank.width(), v._lbl_bank.minimumWidth())

    def test_popout_und_zurueckholen(self):
        v = self.view
        vorher = (self._lage_taste(), self._lage_konsole())
        v._popout_canvas()
        self.app.processEvents()
        fenster = v._popout_window
        try:
            lage_im_popout = self.taste.mapTo(fenster, QPoint(0, 0))
            self.fm.start(self.fn.id)
            self._takt()
            self.assertEqual(self.taste.mapTo(fenster, QPoint(0, 0)), lage_im_popout)
            self.fm.stop(self.fn.id)
            self._takt()
            self.assertEqual(self.taste.mapTo(fenster, QPoint(0, 0)), lage_im_popout)
            self.fm.start(self.fn.id)
            self._takt()
        finally:
            fenster.close()
            self.app.processEvents()
        self._takt()
        self.assertIsNone(v._popout_window)
        self.assertEqual((self._lage_taste(), self._lage_konsole()), vorher)
        self.fm.stop(self.fn.id)
        self._takt()
        self.assertEqual((self._lage_taste(), self._lage_konsole()), vorher)

    def test_groessere_programmschrift_aendert_nichts(self):
        v = self.view
        alt = self.app.font()
        gross = QFont(alt)
        gross.setPointSize(max(1, alt.pointSize()) * 2)
        self.app.setFont(gross)
        try:
            self.app.processEvents()
            for breite in range(540, 1500, 40):
                v.resize(breite, self.HOEHE)
                self.app.processEvents()
                self.app.processEvents()
                vorher = self._oben()
                for knopf in (v._btn_pickup, v._btn_touch_lock):
                    for zustand in (True, False):
                        knopf.setChecked(zustand)
                        self.app.processEvents()
                        self.app.processEvents()
                        self.assertEqual(self._oben(), vorher, f"Breite {breite}")
                self.fm.start(self.fn.id)
                self._takt()
                self.assertEqual(self._oben(), vorher, f"Breite {breite}")
                self.assertEqual(v._lbl_active_fx.height(), v._ZEILE_AKTIVER_EFFEKT_H)
                self.fm.stop(self.fn.id)
                self._takt()
        finally:
            self.app.setFont(alt)
            self.app.processEvents()


class _ImHauptfenster(unittest.TestCase):
    """Die Konsole im echten Hauptfenster (Thema, Kopfleisten, Kiosk-Streifen).
    Gemessen wird in Fensterkoordinaten — dort, wo der Finger tippt."""

    KIOSK = False
    __test__ = False

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        import src.ui.main_window as MW
        cls.fm = get_state().function_manager
        cls.fm.stop_all()
        cls.fn = cls.fm.new_efx("VCB47-Hauptfenster")
        cls._lock_vorher = VCWidget.input_locked
        cls._pickup_vorher = VCSlider.soft_takeover
        cls.w = MW.MainWindow(kiosk=cls.KIOSK)
        cls.w.resize(1100, 700)
        cls.w.show()
        cls.view = cls.w._vc_view
        cls.w._stack.setCurrentIndex(cls.w._stack.indexOf(cls.view))
        cls.app.processEvents()
        cls.view._active_fx_timer.stop()
        cls.taste = cls.view._canvas._add_widget("VCButton", QPoint(120, 80))
        cls.taste.action = ButtonAction.FUNCTION_TOGGLE
        cls.taste.function_id = cls.fn.id
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.fm.stop(cls.fn.id)
        cls.fm.remove(cls.fn.id)
        VCWidget.input_locked = cls._lock_vorher
        VCSlider.soft_takeover = cls._pickup_vorher
        cls.w._state.laser_estop_active = cls._estop_vorher
        cls.w.hide()
        cls.w.deleteLater()
        cls.app.processEvents()

    def setUp(self):
        type(self)._estop_vorher = getattr(type(self), "_estop_vorher", bool(
            getattr(self.w._state, "laser_estop_active", False)))
        self.view._active_fx_timer.stop()
        self.fm.stop(self.fn.id)
        self._takt()

    def _takt(self):
        self.view._update_active_fx()
        self.app.processEvents()
        self.app.processEvents()

    def _lage(self):
        return self.taste.mapTo(self.w, QPoint(0, 0))

    def test_erster_klick_verschiebt_die_taste_im_fenster_nicht(self):
        vorher = self._lage()
        mitte = self.taste.mapTo(self.w, self.taste.rect().center())
        self.assertIs(self.w.childAt(mitte), self.taste)
        QTest.mouseClick(self.taste, Qt.MouseButton.LeftButton)
        self.assertTrue(self.fn.is_running)
        self._takt()
        self.assertEqual(self._lage(), vorher)
        self.assertIs(self.w.childAt(mitte), self.taste)
        self.fm.stop(self.fn.id)
        self._takt()
        self.assertEqual(self._lage(), vorher)

    def test_umschaltknoepfe_behalten_ihre_breite_auch_mit_programmthema(self):
        """Die Mindestbreite wird beim Bau gemessen, bevor der Knopf im Fenster
        sitzt. Das Programmthema darf die Messung nicht entwerten."""
        v = self.view
        vorher_lage = self._lage()
        for knopf in (v._btn_pickup, v._btn_touch_lock, v._btn_midi_learn):
            breite = knopf.width()
            knopf.setChecked(True)
            self.app.processEvents()
            self.app.processEvents()
            self.assertEqual(knopf.width(), breite, knopf.text())
            self.assertLessEqual(knopf.sizeHint().width(), knopf.minimumWidth(), knopf.text())
            self.assertEqual(self._lage(), vorher_lage, knopf.text())
            knopf.setChecked(False)
            self.app.processEvents()
            self.app.processEvents()
            self.assertEqual(knopf.width(), breite, knopf.text())
            self.assertLessEqual(knopf.sizeHint().width(), knopf.minimumWidth(), knopf.text())
            self.assertEqual(self._lage(), vorher_lage, knopf.text())

    def test_laser_notaus_und_kopfzeilen_verschieben_die_konsole_nicht(self):
        """Sicherheitsanzeigen bleiben sichtbar und unveraendert — sie duerfen
        nur die Tasten nicht verschieben (Blinken, Text „… AKTIV“, Sperrzonen-
        Hinweis, Validierungs- und Fremdwert-Hinweis in der Sektionsleiste)."""
        w = self.w
        vorher = self._lage()
        knopf = w._btn_laser_notaus
        self.assertTrue(knopf.isVisible(), "Der Laser-NOT-AUS muss sichtbar sein.")
        groesse = knopf.size()
        w._state.laser_estop_active = True
        try:
            for _ in range(3):
                w._notaus_tick()
                self.app.processEvents()
                self.assertEqual(self._lage(), vorher)
                self.assertEqual(knopf.size(), groesse)
        finally:
            w._state.laser_estop_active = self._estop_vorher
            w._sync_notaus_button()
            self.app.processEvents()
        self.assertEqual(self._lage(), vorher)
        zeile = getattr(w, "_sperrzonen_kopfzeile", None)
        if zeile is not None:
            war_sichtbar, text = not zeile.isHidden(), zeile.text()
            zeile.setText("Sperrzonen: 3 aktiv")
            zeile.setVisible(True)
            self.app.processEvents()
            self.assertEqual(self._lage(), vorher)
            zeile.setText(text)
            zeile.setVisible(war_sichtbar)
            self.app.processEvents()
        for lbl in (w._lbl_validation, w._lbl_foreign):
            war_versteckt, text = lbl.isHidden(), lbl.text()
            lbl.setText("⚠ 12 Hinweise in dieser Show")
            lbl.show()
            self.app.processEvents()
            self.assertEqual(self._lage(), vorher)
            lbl.setText(text)
            lbl.setHidden(war_versteckt)
            self.app.processEvents()
        self.assertEqual(self._lage(), vorher)


class ImHauptfensterTest(_ImHauptfenster):
    __test__ = True


class ImKioskFensterTest(_ImHauptfenster):
    KIOSK = True
    __test__ = True

    def test_kiosk_zeigt_die_statuszeile_ebenfalls_fest(self):
        self.assertTrue(self.view._lbl_active_fx.isVisible())
        self.assertEqual(self.view._lbl_active_fx.height(),
                         self.view._ZEILE_AKTIVER_EFFEKT_H)


if __name__ == "__main__":
    unittest.main()
