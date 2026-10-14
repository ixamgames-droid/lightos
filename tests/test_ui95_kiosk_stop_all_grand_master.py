"""UI-95: STOP ALL und Grand Master sind auch im Kiosk-Modus sichtbar und
bedienbar.

Im Kiosk-Modus sind Menue- und Sektionsleiste ausgeblendet. LAS-31 hat
BLACKOUT in den Streifen oben rechts neben LASER NOT-AUS gebracht; jetzt stehen
dort auch der Grand-Master-Regler (mit Prozentanzeige) und STOP ALL. Reihenfolge
von links nach rechts: GM, STOP ALL, BLACKOUT, LASER NOT-AUS.

Eine Quelle der Wahrheit: der Regler liest und schreibt
``output_manager.grand_master`` und folgt fremden Aenderungen (VC-Fader, MIDI,
Web). STOP ALL hat keinen Zustand und loest ueber denselben Weg aus wie der
Knopf der Sektionsleiste (``MainWindow._stop_all``).

Eigene Datei, weil hier ein ganzes ``MainWindow`` im Kiosk-Modus gebaut wird.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRect, Qt               # noqa: E402
from PySide6.QtGui import QWheelEvent                               # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton             # noqa: E402

import src.ui.main_window as MW                                     # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _rect(w, win):
    return QRect(w.mapTo(win, QPoint(0, 0)), w.size())


class KioskStopAllUndGrandMasterTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _app()
        cls.w = MW.MainWindow(kiosk=True, touch=True)
        cls.w._hw_timer.stop()
        cls.w.resize(1280, 800)
        cls.w.show()
        _app().processEvents()
        cls.om = cls.w._state.output_manager

    @classmethod
    def tearDownClass(cls):
        try:
            cls.om.set_grand_master(1.0)
            cls.om.set_blackout(False)
        except Exception:
            pass
        cls.w.hide()
        cls.w.deleteLater()
        _app().processEvents()

    def setUp(self):
        self.om.set_grand_master(1.0)
        _app().processEvents()
        self.gm = self.w._slider_gm_kiosk
        self.gm_wert = self.w._lbl_gm_val_kiosk
        self.stop = self.w._btn_stop_all_kiosk
        self.bo = self.w._btn_blackout_kiosk
        self.notaus = self.w._btn_laser_notaus

    def tearDown(self):
        self.om.set_grand_master(1.0)
        _app().processEvents()

    def _knoepfe(self):
        return [("GM", self.gm.parentWidget()), ("STOP ALL", self.stop),
                ("BLACKOUT", self.bo), ("NOT-AUS", self.notaus)]

    # ── Sichtbar und an der richtigen Stelle ─────────────────────────────

    def test_sichtbar_im_streifen_in_der_reihenfolge(self):
        self.assertTrue(self.w._section_bar.isHidden())
        leiste = self.w._notaus_leiste
        for name, wdg in self._knoepfe():
            self.assertTrue(wdg.isVisible(), f"{name} nicht sichtbar")
            self.assertTrue(wdg.isEnabled(), f"{name} nicht bedienbar")
        self.assertIs(self.gm.parentWidget().parentWidget(), leiste)
        self.assertIs(self.stop.parentWidget(), leiste)
        self.assertEqual(self.stop.text(), "STOP ALL")
        self.assertEqual(self.gm_wert.text(), "100%")
        rects = [_rect(wdg, self.w) for _n, wdg in self._knoepfe()]
        for links, rechts in zip(rects, rects[1:]):
            self.assertLess(links.right(), rechts.left(), "Reihenfolge/Ueberlappung")
        self.assertGreaterEqual(self.stop.height(), 38, "Touch: fingergross")
        self.assertTrue(self.stop.toolTip())
        self.assertTrue(self.gm.toolTip())

    def test_ohne_kiosk_keine_zweiten_bedienelemente(self):
        w = MW.MainWindow(kiosk=False)
        try:
            w._hw_timer.stop()
            self.assertIsNone(getattr(w, "_slider_gm_kiosk", None))
            self.assertIsNone(getattr(w, "_btn_stop_all_kiosk", None))
        finally:
            w.deleteLater()
            _app().processEvents()

    # ── Grand Master: eine Quelle der Wahrheit ───────────────────────────

    def test_regler_schreibt_grand_master(self):
        self.gm.setValue(40)
        _app().processEvents()
        self.assertAlmostEqual(self.om.grand_master, 0.40, places=3)
        self.assertEqual(self.gm_wert.text(), "40%")
        # der (ausgeblendete) Regler der Sektionsleiste zieht mit
        self.assertEqual(self.w._slider_gm.value(), 40)
        self.assertEqual(self.w._lbl_gm_val.text(), "40%")

    def test_regler_folgt_fremder_aenderung(self):
        """VC-Fader, MIDI und Web aendern ueber ``set_grand_master``."""
        self.om.set_grand_master(0.25)
        _app().processEvents()
        self.assertEqual(self.gm.value(), 25)
        self.assertEqual(self.gm_wert.text(), "25%")
        self.om.set_grand_master(0.0)
        _app().processEvents()
        self.assertEqual(self.gm.value(), 0)
        self.assertEqual(self.gm_wert.text(), "0%")

    def test_nachziehen_schreibt_nicht_zurueck(self):
        """Das Nachziehen loest kein erneutes ``set_grand_master`` aus
        (kein Rueckkopplungs-Kreis mit dem VC-Fader)."""
        aufrufe = []
        orig = self.om.set_grand_master

        def mitschreiber(val):
            aufrufe.append(val)
            orig(val)
        self.om.set_grand_master = mitschreiber
        try:
            mitschreiber(0.6)
            _app().processEvents()
        finally:
            del self.om.set_grand_master
        self.assertEqual(aufrufe, [0.6])
        self.assertEqual(self.gm.value(), 60)

    def test_mausrad_verstellt_den_regler_nicht(self):
        self.gm.setValue(50)
        _app().processEvents()
        self.assertFalse(self.gm.hasFocus())
        mitte = QPointF(self.gm.width() / 2, self.gm.height() / 2)
        for delta in (120, -120, 480):
            ev = QWheelEvent(mitte, QPointF(self.gm.mapToGlobal(mitte.toPoint())),
                             QPoint(0, 0), QPoint(0, delta),
                             Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                             Qt.ScrollPhase.NoScrollPhase, False)
            QApplication.sendEvent(self.gm, ev)
        _app().processEvents()
        self.assertEqual(self.gm.value(), 50)
        self.assertAlmostEqual(self.om.grand_master, 0.50, places=3)

    def test_kein_tastaturfokus(self):
        self.assertEqual(self.stop.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertEqual(self.gm.focusPolicy(), Qt.FocusPolicy.NoFocus)

    # ── STOP ALL: derselbe Weg wie die Sektionsleiste ────────────────────

    def _stop_mitschreiben(self):
        st = self.w._state
        aufrufe = []
        pe, fm = st.playback_engine, st.function_manager
        alt_pe, alt_fm = pe.stop_all, fm.stop_all
        pe.stop_all = lambda *a, **k: (aufrufe.append("playback"), alt_pe(*a, **k))
        fm.stop_all = lambda *a, **k: (aufrufe.append("funktionen"), alt_fm(*a, **k))

        def zurueck():
            del pe.stop_all
            del fm.stop_all
        return aufrufe, zurueck

    def test_stop_all_stoppt_wie_die_sektionsleiste(self):
        kopf = [b for b in self.w._section_bar.findChildren(QPushButton)
                if b.text() == "STOP ALL"]
        self.assertEqual(len(kopf), 1)
        aufrufe, zurueck = self._stop_mitschreiben()
        try:
            self.stop.click()
            kiosk = list(aufrufe)
            aufrufe.clear()
            kopf[0].click()
            leiste = list(aufrufe)
        finally:
            zurueck()
        self.assertEqual(kiosk, ["playback", "funktionen"])
        self.assertEqual(kiosk, leiste, "anderer Weg als die Sektionsleiste")

    def test_stop_all_laesst_gm_und_blackout_stehen(self):
        self.om.set_grand_master(0.3)
        _app().processEvents()
        self.stop.click()
        _app().processEvents()
        self.assertAlmostEqual(self.om.grand_master, 0.3, places=3)
        self.assertFalse(self.om.blackout)
        self.assertEqual(self.gm.value(), 30)

    def test_leertaste_loest_nichts_aus(self):
        """Leertaste ist GO — sie darf STOP ALL nicht ausloesen und den GM
        nicht verstellen."""
        from PySide6.QtTest import QTest
        self.gm.setValue(70)
        self.stop.click()
        _app().processEvents()
        self.assertNotIn(QApplication.focusWidget(), (self.stop, self.gm))
        aufrufe, zurueck = self._stop_mitschreiben()
        try:
            ziel = QApplication.focusWidget() or self.w
            QTest.keyClick(ziel, Qt.Key.Key_Space)
            _app().processEvents()
        finally:
            zurueck()
        self.assertEqual(aufrufe, [], "Leertaste loeste STOP ALL aus")
        self.assertEqual(self.gm.value(), 70)
        self.assertAlmostEqual(self.om.grand_master, 0.70, places=3)

    # ── Platz ────────────────────────────────────────────────────────────

    def test_groesse_und_lage_bei_kleinem_und_grossem_bildschirm(self):
        """1024x600 (kleines Touch-Pult) und 1920x1080: alles ganz im Fenster,
        nebeneinander, nicht gequetscht."""
        try:
            for breite, hoehe in ((1024, 600), (1920, 1080)):
                self.w.resize(breite, hoehe)
                _app().processEvents()
                fenster = QRect(0, 0, self.w.width(), self.w.height())
                rects = []
                for name, wdg in self._knoepfe():
                    r = _rect(wdg, self.w)
                    self.assertTrue(fenster.contains(r),
                                    f"{name} ragt bei {breite}x{hoehe} hinaus")
                    self.assertGreaterEqual(
                        wdg.width(), wdg.minimumSizeHint().width(),
                        f"{name} bei {breite}x{hoehe} gequetscht")
                    rects.append(r)
                for i, a in enumerate(rects):
                    for b in rects[i + 1:]:
                        self.assertFalse(a.intersects(b),
                                         f"Ueberlappung bei {breite}x{hoehe}")
                self.assertGreaterEqual(self.gm.width(), 100)
                self.assertGreaterEqual(
                    self.gm_wert.width(),
                    self.gm_wert.fontMetrics().horizontalAdvance("100%"))
        finally:
            self.w.resize(1280, 800)
            _app().processEvents()

    def test_banner_und_chip_verdecken_nichts(self):
        """Ausgabe-Banner und Chip (VCB-47) ueberlagern nur den
        Ansichtsstapel — der Streifen liegt im Layout darueber."""
        import io
        from contextlib import redirect_stdout

        class _Manager:
            def ausgabe_status(self):
                return [{"universum": 1, "weg": "Enttec", "ziel": "COM9",
                         "verbunden": False, "problem": ""}]

        steuerung = self.w._ausgabe_banner
        groessen = ((1024, 600), (1920, 1080))
        try:
            with redirect_stdout(io.StringIO()):
                steuerung.aktualisiere(_Manager())
            for breite, hoehe in groessen:
                self.w.resize(breite, hoehe)
                _app().processEvents()
                r_stack = _rect(self.w._stack, self.w)
                banner = steuerung.widget
                self.assertTrue(banner.isVisibleTo(self.w))
                r_b = _rect(banner, self.w)
                for name, wdg in self._knoepfe():
                    r_k = _rect(wdg, self.w)
                    self.assertFalse(r_k.intersects(r_b),
                                     f"{name} und Banner bei {breite}x{hoehe}")
                    self.assertLess(r_k.bottom(), r_stack.top())
            steuerung.klappe_ein()
            for breite, hoehe in groessen:
                self.w.resize(breite, hoehe)
                _app().processEvents()
                chip = steuerung.chip
                if chip.isVisibleTo(self.w):
                    r_c = _rect(chip, self.w)
                    for name, wdg in self._knoepfe():
                        self.assertFalse(_rect(wdg, self.w).intersects(r_c),
                                         f"{name} und Chip bei {breite}x{hoehe}")
                for name, wdg in self._knoepfe():
                    self.assertTrue(wdg.isVisible(), name)
        finally:
            class _Gut:
                def ausgabe_status(self):
                    return []
            from src.ui.ausgabe_banner import HALTE_S
            t = [steuerung._uhr() + HALTE_S + 1.0]
            alt = steuerung._uhr
            steuerung._uhr = lambda: t[0]
            with redirect_stdout(io.StringIO()):
                steuerung.aktualisiere(_Gut())
                t[0] += HALTE_S + 1.0
                steuerung.aktualisiere(_Gut())
            steuerung._uhr = alt
            self.w.resize(1280, 800)
            _app().processEvents()


if __name__ == "__main__":
    unittest.main()
