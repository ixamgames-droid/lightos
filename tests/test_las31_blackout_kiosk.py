"""LAS-31 (Rest): BLACKOUT ist auch im Kiosk-Modus sichtbar und bedienbar.

Im Kiosk-Modus sind Menue- und Sektionsleiste ausgeblendet — mit der
Sektionsleiste verschwand auch BLACKOUT. Der Laser-NOT-AUS hat dort einen
eigenen Streifen oben rechts; BLACKOUT steht jetzt im selben Streifen direkt
links daneben. Bedienung und Anzeige wie der Knopf der Sektionsleiste: Klick
schaltet um, die Anzeige liest allein ``output_manager.blackout`` (UI-58) —
auch wenn eine VC-Taste oder die Kommandozeile den Blackout schaltet.

Eigene Datei, weil hier ein ganzes ``MainWindow`` im Kiosk-Modus gebaut wird.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect                             # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

import src.ui.main_window as MW                                      # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _rect(w, win):
    return QRect(w.mapTo(win, QPoint(0, 0)), w.size())


class BlackoutImKioskTest(unittest.TestCase):

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
            cls.om.set_blackout(False)
        except Exception:
            pass
        cls.w.hide()
        cls.w.deleteLater()
        _app().processEvents()

    def setUp(self):
        self.om.set_blackout(False)
        _app().processEvents()
        self.bo = self.w._btn_blackout_kiosk
        self.notaus = self.w._btn_laser_notaus

    def tearDown(self):
        self.om.set_blackout(False)
        _app().processEvents()

    def _rot(self, btn):
        return "#cc0000" in btn.styleSheet()

    def test_sichtbar_im_streifen_neben_dem_notaus(self):
        self.assertTrue(self.w._section_bar.isHidden())
        self.assertTrue(self.bo.isVisible())
        self.assertTrue(self.bo.isEnabled())
        self.assertEqual(self.bo.text(), "BLACKOUT")
        self.assertTrue(self.bo.isCheckable())
        self.assertIs(self.bo.parentWidget(), self.w._notaus_leiste)
        self.assertIs(self.notaus.parentWidget(), self.w._notaus_leiste)
        r_bo, r_na = _rect(self.bo, self.w), _rect(self.notaus, self.w)
        self.assertLess(r_bo.right(), r_na.left(), "links neben dem NOT-AUS")
        self.assertFalse(r_bo.intersects(r_na), "keine Ueberlappung")
        self.assertGreaterEqual(self.bo.height(), 38, "Touch: fingergross")
        self.assertGreaterEqual(self.bo.width(), self.bo.minimumSizeHint().width(),
                                "Text nicht gequetscht")
        self.assertTrue(self.bo.toolTip())

    def test_banner_und_chip_verdecken_nichts(self):
        """Das Ausgabe-Banner und sein Chip (VCB-47) ueberlagern nur den
        Ansichtsstapel — der Streifen liegt im Layout darueber, sie schneiden
        sich nicht."""
        import io
        from contextlib import redirect_stdout

        class _Manager:
            def ausgabe_status(self):
                return [{"universum": 1, "weg": "Enttec", "ziel": "COM9",
                         "verbunden": False, "problem": ""}]

        steuerung = self.w._ausgabe_banner
        with redirect_stdout(io.StringIO()):
            steuerung.aktualisiere(_Manager())
        _app().processEvents()
        r_stack = _rect(self.w._stack, self.w)
        knoepfe = (self.bo, self.notaus)
        try:
            banner = steuerung.widget
            self.assertTrue(banner.isVisibleTo(self.w))
            r_b = _rect(banner, self.w)
            self.assertGreaterEqual(r_b.top(), r_stack.top())
            for knopf in knoepfe:
                r_k = _rect(knopf, self.w)
                self.assertFalse(r_k.intersects(r_b),
                                 f"{knopf.text()} und Banner ueberlappen")
                self.assertLess(r_k.bottom(), r_stack.top())
            steuerung.klappe_ein()
            _app().processEvents()
            chip = steuerung.chip
            if chip.isVisibleTo(self.w):
                r_c = QRect(chip.mapTo(self.w, QPoint(0, 0)), chip.size())
                for knopf in knoepfe:
                    self.assertFalse(_rect(knopf, self.w).intersects(r_c),
                                     f"{knopf.text()} und Chip ueberlappen")
            self.assertTrue(self.bo.isVisible())
            self.assertTrue(self.notaus.isVisible())
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

    def test_klick_schaltet_blackout(self):
        self.bo.click()
        self.assertTrue(self.om.blackout)
        self.assertTrue(self.bo.isChecked())
        self.assertTrue(self._rot(self.bo))
        self.bo.click()
        self.assertFalse(self.om.blackout)
        self.assertFalse(self.bo.isChecked())
        self.assertFalse(self._rot(self.bo))

    def test_anzeige_folgt_fremdem_schalten(self):
        """Kommandozeile/Web/OSC schalten ueber ``set_blackout`` — der Knopf
        zieht nach (eine Quelle der Wahrheit), ebenso der ausgeblendete der
        Sektionsleiste."""
        self.om.set_blackout(True)
        _app().processEvents()
        self.assertTrue(self.bo.isChecked())
        self.assertTrue(self._rot(self.bo))
        self.assertTrue(self.w._btn_blackout.isChecked())
        self.om.set_blackout(False)
        _app().processEvents()
        self.assertFalse(self.bo.isChecked())
        self.assertFalse(self.w._btn_blackout.isChecked())

    def test_anzeige_folgt_der_vc_taste(self):
        """Eine gehaltene VC-Blackout-Taste (VCB-43): der Knopf zeigt dunkel,
        solange sie gehalten wird; ein Klick auf „aus“ macht nicht hell."""
        self.om.halte_blackout("vc-test", True)
        _app().processEvents()
        try:
            self.assertTrue(self.bo.isChecked())
            self.bo.click()                    # Schalter aus — Taste haelt weiter
            self.assertTrue(self.om.blackout)
            self.assertTrue(self.bo.isChecked())
        finally:
            self.om.halte_blackout("vc-test", False)
            _app().processEvents()
        self.assertFalse(self.om.blackout)
        self.assertFalse(self.bo.isChecked())

    def test_kein_tastaturfokus(self):
        from PySide6.QtCore import Qt
        self.assertEqual(self.bo.focusPolicy(), Qt.FocusPolicy.NoFocus)

    def test_groesse_und_lage_bei_kleinem_und_grossem_bildschirm(self):
        """Gegenpruefung: 1024x600 (kleines Touch-Pult) und 1920x1080 —
        beide Knoepfe ganz im Fenster, nebeneinander, nicht gequetscht."""
        fenster = QRect(0, 0, 0, 0)
        try:
            for breite, hoehe in ((1024, 600), (1920, 1080)):
                self.w.resize(breite, hoehe)
                _app().processEvents()
                fenster = QRect(0, 0, self.w.width(), self.w.height())
                r_bo, r_na = _rect(self.bo, self.w), _rect(self.notaus, self.w)
                for r, name in ((r_bo, "BLACKOUT"), (r_na, "NOT-AUS")):
                    self.assertTrue(fenster.contains(r),
                                    f"{name} ragt bei {breite}x{hoehe} hinaus")
                self.assertFalse(r_bo.intersects(r_na))
                self.assertLess(r_bo.right(), r_na.left())
                self.assertGreaterEqual(self.bo.width(),
                                        self.bo.minimumSizeHint().width())
                self.assertGreaterEqual(self.notaus.width(),
                                        self.notaus.minimumSizeHint().width())
        finally:
            self.w.resize(1280, 800)
            _app().processEvents()

    def test_leertaste_loest_keinen_blackout_aus(self):
        """Leertaste ist GO — sie darf den Kiosk-BLACKOUT nie schalten."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.bo.click()
        self.bo.click()                      # einmal an, einmal aus
        _app().processEvents()
        self.assertFalse(self.om.blackout)
        self.assertIsNot(QApplication.focusWidget(), self.bo)
        ziel = QApplication.focusWidget() or self.w
        QTest.keyClick(ziel, Qt.Key.Key_Space)
        _app().processEvents()
        self.assertFalse(self.om.blackout, "Leertaste schaltete BLACKOUT")
        self.assertFalse(self.bo.isChecked())


class OhneKioskKeinZweiterKnopf(unittest.TestCase):
    """Ausserhalb des Kiosk steht BLACKOUT nur in der Sektionsleiste."""

    def test_nur_ein_knopf(self):
        _app()
        w = MW.MainWindow(kiosk=False)
        try:
            w._hw_timer.stop()
            self.assertIsNone(getattr(w, "_btn_blackout_kiosk", None))
            self.assertIsNotNone(w._btn_blackout)
        finally:
            w.deleteLater()
            _app().processEvents()


if __name__ == "__main__":
    unittest.main()
