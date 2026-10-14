"""LAS-31 (Rest): alle drei Ausloeser des Laser-NOT-AUS gehen EINEN Weg.

Kopfleiste (samt Tastenkuerzel), VC-Taste (``ButtonAction.LASER_ESTOP``) und
der NOT-AUS-Knopf der Laser-Seite riefen frueher jeder fuer sich
``estop_all`` -> ``set_armed(False)`` -> ``clear_estop_all`` auf. Jetzt rufen
alle drei ``AppState.laser_notaus_ausloesen`` — eine Stelle, ein Ablauf.

Geprueft wird mit einem Mitschreiber um genau diese Methode und am Ergebnis:
der Laser liegt danach im DMX-Bild auf dem Aus-Wert seines Profils, der
Netzwerk-Ausgang ist unscharf. Der Zustand ist ein ``AppState`` mit echtem
Render-Pfad und echtem ``OutputManager`` ohne Geraete (wie
``test_las31_notaus_kopfleiste.py``).
"""
import os
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                           # noqa: E402

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
# 100-255 „Manual“ — der Aus-Wert ist 50, nicht 0.
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


def _make_state():
    om = OutputManager()
    om.add_universe(1)
    st = AppState.__new__(AppState)
    st.universes = om.universes
    st.programmer = {7: {"shutter": _MANUAL, "laser_bank": 5},
                     9: {"intensity": 200, "color_r": 150}}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = [_LASER, _PAR]
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


class EinWegTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _app()
        cls._orig_channels = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANNELS[fx.fid]
        cls.w = MW.MainWindow(kiosk=False)
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
        self.lo = self.st.ensure_laser_output()
        self.lo.set_armed(True)
        # Mitschreiber: jeder Aufruf des einen Weges wird notiert, der echte
        # Ablauf laeuft trotzdem.
        self.aufrufe = []
        echt = self.st.laser_notaus_ausloesen

        def mitschreiber():
            self.aufrufe.append(1)
            return echt()
        self.st.laser_notaus_ausloesen = mitschreiber
        self.w._state = self.st
        self.w._notaus_sperre_bis = 0.0
        p = mock.patch.object(MW.QMessageBox, "warning",
                              side_effect=AssertionError("unerwartete Rueckfrage"))
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.w._state = self._echter_state

    def _frame(self):
        self.st._render_frame(0.025)
        self.om._send_all()
        return self.om._display_frame[1]

    def _pruefe_dunkel(self, wer):
        self.assertEqual(self.aufrufe, [1],
                         f"{wer}: genau ein Aufruf von laser_notaus_ausloesen")
        self.assertTrue(self.st.laser_estop_active, f"{wer}: Latch steht")
        d = self._frame()
        self.assertEqual(d[9], _AUS, f"{wer}: Aus-Wert des Profils")
        self.assertEqual((d[10], d[11]), (0, 0), f"{wer}: Laser-Kanaele dunkel")
        self.assertEqual(d[19], 200, f"{wer}: der PAR laeuft weiter")
        self.assertFalse(self.lo.armed, f"{wer}: Netzwerk-Laser unscharf")

    def test_vorher_laeuft_der_laser(self):
        self.assertEqual(self._frame()[9], _MANUAL)

    def test_kopfleiste(self):
        self.w._btn_laser_notaus.click()
        self._pruefe_dunkel("Kopfleiste")

    def test_tastenkuerzel(self):
        self.w._sc_laser_notaus.activated.emit()
        self._pruefe_dunkel("Tastenkuerzel")

    def test_vc_taste(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        with mock.patch.object(A, "get_state", lambda: self.st):
            btn = VCButton()
            btn.action = ButtonAction.LASER_ESTOP
            btn.function_id = None
            btn._trigger_primary(True)
            btn._trigger_primary(False)      # Loslassen loest nichts aus
        self._pruefe_dunkel("VC-Taste")

    def test_laser_seite(self):
        import src.ui.views.laser_view as lv
        with mock.patch.object(lv, "get_state", lambda: self.st):
            view = lv.LaserView(follow_selection=False)
            try:
                view._btn_arm.setChecked(True)
                self.aufrufe.clear()
                self.lo.set_armed(True)
                view._btn_dmx_estop.click()
                self._pruefe_dunkel("Laser-Seite")
                self.assertFalse(view._btn_arm.isChecked(),
                                 "der Scharf-Knopf zeigt danach unscharf")
            finally:
                view.deleteLater()
                _app().processEvents()

    def test_keine_eigenen_drei_schritte_mehr(self):
        """Quelltext-Waechter: VC-Taste und Laser-Seite rufen die Schritte
        nicht mehr selbst auf (sonst laufen die Wege wieder auseinander)."""
        import inspect
        from src.ui.virtualconsole import vc_button
        import src.ui.views.laser_view as lv
        def ohne_kommentare(text):
            return "\n".join(z.split("#", 1)[0] for z in text.splitlines())
        quelle = ohne_kommentare(inspect.getsource(lv.LaserView._on_estop))
        for schritt in ("estop_all(", "clear_estop_all(", "set_armed("):
            self.assertNotIn(schritt, quelle, f"Laser-Seite: {schritt}")
        vc = ohne_kommentare(inspect.getsource(vc_button))
        block = vc.split("if self.action == ButtonAction.LASER_ESTOP:", 1)[1]
        block = block.split("if self.action ==", 1)[0]
        self.assertIn("laser_notaus_ausloesen()", block)
        for schritt in ("estop_all(", "clear_estop_all(", "set_armed("):
            self.assertNotIn(schritt, block, f"VC-Taste: {schritt}")


class AusnahmeImSchrittTest(unittest.TestCase):
    """Gegenpruefung: wirft ein Schritt des einen Weges, laufen die anderen
    trotzdem — vorher sprang eine Ausnahme in ``estop_all`` ueber das
    Entwaffnen hinweg, ein Netzwerk-Laser blieb scharf."""

    def setUp(self):
        _app()
        self.st, self.om = _make_state()
        self.lo = self.st.ensure_laser_output()
        self.lo.set_armed(True)

    def test_estop_all_wirft_trotzdem_unscharf_und_latch(self):
        def wirft():
            self.lo._estopped = True
            raise RuntimeError("Netzwerk weg")
        self.lo.estop_all = wirft
        self.st.laser_notaus_ausloesen()
        self.assertFalse(self.lo.armed, "Netzwerk-Laser muss unscharf sein")
        self.assertTrue(self.st.laser_estop_active, "DMX-Latch muss stehen")

    def test_entwaffnen_wirft_verriegelung_bleibt(self):
        def wirft(_wert):
            raise RuntimeError("kaputt")
        self.lo.set_armed = wirft
        self.st.laser_notaus_ausloesen()
        self.assertTrue(self.lo._estopped,
                        "bleibt der Manager scharf, wird die Verriegelung "
                        "nicht geloest — im Zweifel dunkel")
        self.assertTrue(self.st.laser_estop_active)

    def test_laser_seite_zeigt_echten_stand(self):
        import src.ui.views.laser_view as lv
        with mock.patch.object(lv, "get_state", lambda: self.st):
            view = lv.LaserView(follow_selection=False)
            try:
                view._btn_arm.setChecked(True)
                self.lo.set_armed(True)
                echt = self.lo.set_armed
                self.lo.set_armed = lambda w: (None if not w else echt(w))
                view._btn_dmx_estop.click()
                self.assertTrue(self.lo.armed)
                self.assertTrue(view._btn_arm.isChecked(),
                                "der Knopf darf nicht unscharf zeigen, "
                                "waehrend der Manager scharf ist")
            finally:
                view.deleteLater()
                _app().processEvents()


if __name__ == "__main__":
    unittest.main()
