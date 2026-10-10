"""LAS-31: fester Laser-NOT-AUS in der Kopfleiste des Hauptfensters.

Bisher gab es den Laser-NOT-AUS nur als selbst angelegte VC-Taste und als Knopf
auf der Laser-Seite — wer keine Taste gebaut hatte oder gerade woanders war,
hatte keinen. Jetzt sitzt er oben rechts neben BLACKOUT, auch im Kiosk-Modus
(dort ist die Sektionsleiste samt BLACKOUT ausgeblendet).

Getestet am echten ``MainWindow`` (offscreen). Der Zustand dahinter ist ein
``AppState`` mit echtem Render-Pfad und echtem ``OutputManager`` ohne Geraete:
``_render_frame`` -> ``_send_all`` -> Display-Frame — der Knopf muss an der
Laser-Adresse den AUS-Wert des Profils erzeugen, nicht bloss ein Flag setzen.
"""
import os
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                        # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from src.core.app_state import AppState                              # noqa: E402
from src.core.dmx.output_manager import OutputManager                # noqa: E402
import src.ui.main_window as MW                                      # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


class _Rg:
    def __init__(self, von, bis, name, kind=""):
        self.range_from, self.range_to, self.name, self.kind = von, bis, name, kind


class _Ch:
    def __init__(self, attr, num, ranges=(), default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default
        self.ranges = list(ranges)
        self.name = attr


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 3
    protocol = ""

    def __init__(self, fid, universe, address, ftype=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = ftype
        self.fixture_name = f"fx{fid}"


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


# Laser auf 10: Betriebsart 0-49 „Auto“ (DMX 0 = AN!), 50-99 „Laser off“,
# 100-255 „Manual“ — der Aus-Wert ist also 50, nicht 0 (wie in LAS-25).
_LASER = _Fx(7, 1, 10, "laser")
_PAR = _Fx(9, 1, 20)
_CHANNELS = {
    7: [_Ch("shutter", 1, [_Rg(0, 49, "Auto run", "open"),
                           _Rg(50, 99, "Laser off", "closed"),
                           _Rg(100, 255, "Manual", "open")]),
        _Ch("laser_bank", 2), _Ch("laser_x", 3)],
    9: [_Ch("intensity", 1), _Ch("color_r", 2)],
}
_AUS = 50
_MANUAL = 120


def _make_state(patch=(_LASER, _PAR)):
    om = OutputManager()
    om.add_universe(1)
    st = AppState.__new__(AppState)
    st.universes = om.universes
    st.programmer = {7: {"shutter": _MANUAL, "laser_bank": 5},
                     9: {"intensity": 200, "color_r": 150}}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = list(patch)
    st._prog_lock = threading.RLock()
    st.output_manager = om
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st._emit = lambda *a, **k: None
    st._rebuild_render_plan()
    return st, om


class _Basis(unittest.TestCase):
    KIOSK = False
    TOUCH = False

    @classmethod
    def setUpClass(cls):
        _app()
        cls._orig_channels = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANNELS[fx.fid]
        cls.w = MW.MainWindow(kiosk=cls.KIOSK, touch=cls.TOUCH)
        cls._echter_state = cls.w._state
        cls.w.show()
        _app().processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.w._state = cls._echter_state
        cls.w.hide()
        cls.w.deleteLater()
        _app().processEvents()
        A.get_channels_for_patched = cls._orig_channels

    def setUp(self):
        self.st, self.om = _make_state()
        self.w._state = self.st
        self.w._notaus_sperre_bis = 0.0
        self.w._sync_notaus_button()
        self.btn = self.w._btn_laser_notaus
        # Eine unerwartete Rueckfrage darf den Lauf nie blockieren.
        p = mock.patch.object(MW.QMessageBox, "warning",
                              side_effect=AssertionError("unerwartete Rueckfrage"))
        self.frage = p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.w._state = self._echter_state

    def _frame(self):
        self.st._render_frame(0.025)
        self.om._send_all()
        return self.om._display_frame[1]

    def _antwort(self, knopf):
        self.frage.side_effect = None
        self.frage.return_value = knopf


class KnopfTest(_Basis):

    def test_knopf_steht_oben_rechts_ueber_blackout(self):
        """Rechte Ecke der Menueleiste, direkt ueber BLACKOUT — in der
        Sektionsleiste ist bei 1440 px kein Platz mehr (UI-25)."""
        self.assertTrue(self.btn.isVisible())
        self.assertTrue(self.btn.isEnabled())
        self.assertEqual(self.btn.text(), "LASER NOT-AUS")
        self.assertIs(self.btn.parentWidget().parentWidget(), self.w.menuBar())
        for breite in (900, 1280, 1440):
            self.w.resize(breite, 700)
            _app().processEvents()
            g = self.btn.rect()
            links = self.btn.mapTo(self.w, g.topLeft())
            rechts = self.btn.mapTo(self.w, g.bottomRight())
            self.assertLessEqual(rechts.x(), self.w.width(), f"{breite}: abgeschnitten")
            self.assertGreater(links.x(), self.w.width() // 2, f"{breite}: nicht rechts")
            bo = self.w._btn_blackout
            self.assertLessEqual(rechts.y(), bo.mapTo(self.w, bo.rect().topLeft()).y(),
                                 "ueber BLACKOUT")
            self.assertGreaterEqual(g.width(), self.btn.minimumSizeHint().width(),
                                    f"{breite}: Text gequetscht")
        self.assertFalse(self.btn.isCheckable(),
                         "kein Rast-Knopf: der Zustand kommt allein vom Latch")

    def test_ein_klick_loest_aus_ohne_rueckfrage(self):
        self.assertEqual(self._frame()[9], _MANUAL)       # Laser laeuft
        self.btn.click()
        self.frage.assert_not_called()
        self.assertTrue(self.st.laser_estop_active)
        d = self._frame()
        self.assertEqual(d[9], _AUS, "Aus-Wert des Profils, nicht 0 (= Auto, an)")
        self.assertEqual((d[10], d[11]), (0, 0))
        self.assertEqual(d[19], 200, "der PAR laeuft weiter")
        self.assertTrue(self.om._laser_estop_aktiv)

    def test_klick_entschaerft_auch_den_netzwerk_laser(self):
        lo = self.st.ensure_laser_output()
        lo.set_armed(True)
        self.btn.click()
        self.assertFalse(lo.armed)

    def test_anzeige_aktiv(self):
        self.btn.click()
        _app().processEvents()
        self.assertEqual(self.btn.text(), "LASER NOT-AUS AKTIV")
        self.assertGreaterEqual(self.btn.width(), self.btn.sizeHint().width(),
                                "der Aktiv-Text passt ganz auf den Knopf")
        a = self.btn.styleSheet()
        self.w._notaus_tick()
        b = self.btn.styleSheet()
        self.assertNotEqual(a, b, "blinkt: der Takt wechselt die Darstellung")
        self.w._notaus_tick()
        self.assertEqual(self.btn.styleSheet(), a)

    def test_folgt_der_vc_taste(self):
        """Derselbe Weg wie ButtonAction.LASER_ESTOP der Virtuellen Konsole."""
        lo = self.st.ensure_laser_output()
        lo.estop_all()
        lo.set_armed(False)
        lo.clear_estop_all()
        _app().processEvents()
        self.assertEqual(self.btn.text(), "LASER NOT-AUS AKTIV")

    def test_folgt_ausloesung_aus_fremdem_thread(self):
        """MIDI/OSC loesen aus ihrem Thread aus — der Knopf wird im UI-Thread
        nachgefuehrt, nie im Fremd-Thread angefasst."""
        t = threading.Thread(target=self.st.ensure_laser_output().estop_all)
        t.start()
        t.join()
        _app().processEvents()
        self.assertEqual(self.btn.text(), "LASER NOT-AUS AKTIV")

    def test_folgt_stillem_setzen_und_loesen(self):
        """Der Latch kann ohne Ereignis wechseln (Muster-Abruf im Programmer
        loest ihn). Der Knopf liest ihn darum im Takt nach — er fuehrt keinen
        eigenen Zustand."""
        self.st.set_laser_estop(True)
        self.w._notaus_tick()
        self.assertEqual(self.btn.text(), "LASER NOT-AUS AKTIV")
        self.st.set_laser_estop(False)
        self.w._notaus_tick()
        self.assertEqual(self.btn.text(), "LASER NOT-AUS")
        self.assertFalse(hasattr(self.w, "_laser_notaus_aktiv"))

    def test_loesen_nur_mit_bestaetigung(self):
        self.btn.click()
        self.w._notaus_sperre_bis = 0.0                   # Doppelklick-Sperre vorbei
        self._antwort(QMessageBox.StandardButton.Cancel)
        self.btn.click()
        self.assertEqual(self.frage.call_count, 1)
        self.assertTrue(self.st.laser_estop_active, "Abbrechen laesst ihn stehen")
        self.assertEqual(self._frame()[9], _AUS)
        # Vorgabe-Knopf der Rueckfrage ist „Abbrechen“ (Enter/Leertaste loest nicht).
        args = self.frage.call_args[0]
        self.assertEqual(args[-1], QMessageBox.StandardButton.Cancel)

        self.w._notaus_sperre_bis = 0.0
        self._antwort(QMessageBox.StandardButton.Yes)
        self.btn.click()
        self.assertFalse(self.st.laser_estop_active)
        self.assertEqual(self.btn.text(), "LASER NOT-AUS")
        self.assertEqual(self._frame()[9], _MANUAL)
        self.assertFalse(self.om._laser_estop_aktiv)

    def test_loesen_schaltet_netzwerk_laser_nicht_scharf(self):
        lo = self.st.ensure_laser_output()
        lo.set_armed(True)
        self.btn.click()
        self.w._notaus_sperre_bis = 0.0
        self._antwort(QMessageBox.StandardButton.Yes)
        self.btn.click()
        self.assertFalse(self.st.laser_estop_active)
        self.assertFalse(lo.armed, "Scharfschalten bleibt ein eigener, bewusster Schritt")

    def test_doppelklick_loest_nicht(self):
        self._antwort(QMessageBox.StandardButton.Yes)     # selbst ein „Ja“ kaeme nie
        self.btn.click()
        self.btn.click()
        self.btn.click()
        self.frage.assert_not_called()
        self.assertTrue(self.st.laser_estop_active)

    def test_klick_bei_aktivem_latch_loest_erst_erneut_aus(self):
        """Steht der Latch schon, ist aber ein Netzwerk-Laser wieder scharf,
        muss der Klick zuerst abschalten — auch wenn die Rueckfrage abgebrochen
        wird."""
        self.st.set_laser_estop(True)
        lo = self.st.ensure_laser_output()
        lo.set_armed(True)
        self._antwort(QMessageBox.StandardButton.Cancel)
        self.btn.click()
        self.assertFalse(lo.armed)
        self.assertTrue(self.st.laser_estop_active)

    def test_tastenkuerzel(self):
        sc = self.w._sc_laser_notaus
        self.assertEqual(sc.key().toString(), "Ctrl+Shift+L")
        self.assertEqual(sc.context(), Qt.ShortcutContext.ApplicationShortcut)
        self.assertFalse(sc.autoRepeat())
        sc.activated.emit()
        self.assertTrue(self.st.laser_estop_active)
        self.assertEqual(self._frame()[9], _AUS)
        # Das Kuerzel loest nur aus — es fragt nie und loest den Latch nie.
        self.w._notaus_sperre_bis = 0.0
        self._antwort(QMessageBox.StandardButton.Yes)
        sc.activated.emit()
        self.frage.assert_not_called()
        self.assertTrue(self.st.laser_estop_active)

    def test_tastenkuerzel_ist_sonst_frei(self):
        from PySide6.QtGui import QAction
        belegt = [a.text() for a in self.w.findChildren(QAction)
                  if a.shortcut().toString() == "Ctrl+Shift+L"]
        self.assertEqual(belegt, [])

    def test_tooltip_nennt_zahl_und_kuerzel(self):
        self.w._notaus_tick()
        tip = self.btn.toolTip()
        self.assertIn("Erkannte Laser: 1", tip)
        self.assertIn("Strg+Umschalt+L", tip)

    def test_ohne_laser_trotzdem_bedienbar(self):
        self.st, self.om = _make_state(patch=(_PAR,))
        self.w._state = self.st
        self.w._notaus_tick()
        self.assertTrue(self.btn.isEnabled())
        self.assertIn("Erkannte Laser: 0", self.btn.toolTip())
        self.btn.click()
        self.assertTrue(self.st.laser_estop_active)
        self.assertTrue(self.om._laser_estop_aktiv)

    def test_fehler_im_netzwerkteil_setzt_den_latch_trotzdem(self):
        self.st.ensure_laser_output = mock.Mock(side_effect=RuntimeError("kaputt"))
        self.btn.click()
        self.assertTrue(self.st.laser_estop_active)
        self.assertEqual(self._frame()[9], _AUS)


class KioskTouchTest(_Basis):
    """Im Kiosk-Modus ist die Sektionsleiste (mit BLACKOUT) ausgeblendet — der
    NOT-AUS bleibt trotzdem oben rechts stehen."""
    KIOSK = True
    TOUCH = True

    def test_im_kiosk_sichtbar_und_bedienbar(self):
        self.assertFalse(self.w._section_bar.isVisible())
        self.assertTrue(self.btn.isVisible())
        self.assertTrue(self.btn.isEnabled())
        # oben rechts: ueber dem Inhalt, am rechten Rand
        self.assertLess(self.btn.mapTo(self.w, self.btn.rect().topLeft()).y(),
                        self.w._stack.mapTo(self.w, self.w._stack.rect().topLeft()).y())
        self.assertGreater(self.btn.mapTo(self.w, self.btn.rect().center()).x(),
                           self.w.width() // 2)
        self.assertGreaterEqual(self.btn.height(), 38, "Touch: fingergross")
        self.btn.click()
        self.assertTrue(self.st.laser_estop_active)
        self.assertEqual(self._frame()[9], _AUS)
        self.assertEqual(self.btn.text(), "LASER NOT-AUS AKTIV")
        _app().processEvents()
        self.assertGreaterEqual(self.btn.width(), self.btn.sizeHint().width())

    def test_kuerzel_im_kiosk(self):
        self.w._sc_laser_notaus.activated.emit()
        self.assertTrue(self.st.laser_estop_active)


if __name__ == "__main__":
    unittest.main()
