"""LAS-25: Blackout und Ziel-Blackout schalten einen Laser nicht mehr EIN.

LAS-24 zieht Laser ohne Dimmer/Farbe bei GM ~0 auf ihren „aus“-Wert — aber nur
im Grand-Master-Zweig. Der globale Blackout nullte alles (ausser der
Erhalten-Maske), der Ziel-Blackout schrieb danach ebenfalls 0. Der Aus-Wert
ist nicht immer 0: bedeutet DMX 0 an der Betriebsart „Auto“, ging der Laser
gerade beim Blackout an.

Jetzt laufen die Laser-Aus-Werte NACH beiden Blackout-Paessen und VOR dem
NOT-AUS. Getestet ueber den echten Pfad: ``_rebuild_render_plan`` ->
``_render_frame`` -> ``OutputManager._send_all`` -> Display-Frame.
"""
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.output_manager import OutputManager


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


# Laser auf 10: Betriebsart (shutter) 0-49 „Auto“ (DMX 0 = AN!), 50-99
# „Laser off“, 100-255 „Manual“. Aus-Wert also 50, nicht 0.
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


def _make():
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


class BlackoutLaserAusTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANNELS[fx.fid]
        self.st, self.om = _make()

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _frame(self):
        self.st._render_frame(0.025)
        self.om._send_all()
        return self.om._display_frame[1]

    def test_mask_has_non_zero_off_value(self):
        self.assertEqual(self.om._gm_laser_aus_mask, {1: {10: _AUS}})

    def test_normal_laser_runs(self):
        self.assertEqual(self._frame()[9], _MANUAL)

    def test_global_blackout_gm_full_puts_laser_to_off_value(self):
        self.om.grand_master = 1.0
        self.om.set_blackout(True)
        d = self._frame()
        self.assertEqual(d[9], _AUS)         # nicht 0 (= Auto, an)
        self.assertEqual(d[10], 0)           # Muster dunkel
        self.assertEqual(d[19], 0)           # PAR dunkel

    def test_global_blackout_with_gm_zero(self):
        self.om.grand_master = 0.0
        self.om.set_blackout(True)
        self.assertEqual(self._frame()[9], _AUS)

    def test_target_blackout_of_laser(self):
        self.om.grand_master = 1.0
        self.st.set_target_blackout("t1", fids=[7])
        d = self._frame()
        self.assertEqual(d[9], _AUS)
        self.assertEqual(d[19], 200)         # PAR laeuft weiter

    def test_target_blackout_of_other_device_leaves_laser(self):
        self.om.grand_master = 1.0
        self.st.set_target_blackout("t1", fids=[9])
        d = self._frame()
        self.assertEqual(d[9], _MANUAL)
        self.assertEqual(d[19], 0)

    def test_estop_still_wins_over_off_value(self):
        self.om.set_blackout(True)
        self.om.set_laser_estop_mask({1: frozenset({10, 11, 12})})
        d = self._frame()
        self.assertEqual((d[9], d[10], d[11]), (0, 0, 0))

    def test_load_window_blackout(self):
        self.om.set_blackout(True)
        with self.om.lade_sperre():
            self.om.set_gm_laser_aus_mask({})
            self.om._send_all()
            self.assertEqual(self.om._display_frame[1][9], _AUS)


if __name__ == "__main__":
    unittest.main()
