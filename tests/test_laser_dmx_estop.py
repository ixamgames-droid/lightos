"""UXT-12: DMX-Muster-Laser (L2600) beim NOT-AUS wirklich dunkel.

`estop_all()` verriegelt nur den Netzwerk-Streamer — ein Laser, der über normale
DMX-Kanäle ein Muster ausgibt, lief bisher weiter. Der Renderer zwingt jetzt bei
aktivem `laser_estop_active` alle Laser-Kanäle als oberste Ebene auf 0.
"""
import os
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.universe import Universe


class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4
    protocol = ""                      # leer = normaler DMX-Ausgang

    def __init__(self, fid, universe, address, ftype=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = ftype


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


# L2600-artig (laser_*-Kanäle) auf 10..13, ein PAR (kein Laser) auf 20..23.
_LASER = _Fx(7, 1, 10, ftype="laser")
_PAR = _Fx(9, 1, 20)

_CHANNELS = {
    7: [_Ch("laser_bank", 1), _Ch("gobo_wheel", 2),
        _Ch("laser_x", 3), _Ch("shutter", 4)],
    9: [_Ch("intensity", 1), _Ch("color_r", 2),
        _Ch("color_g", 3), _Ch("color_b", 4)],
}


def _make_state():
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = [_LASER, _PAR]
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(
        set_gm_address_mask=lambda m: None)
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True           # _emit ohne UI-Marshaller (Fake-State)
    st._rebuild_render_plan()
    return st


class LaserDmxEstopTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANNELS[fx.fid]
        self.st = _make_state()
        self.live = self.st.universes[1]

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_render_plan_collects_laser_addrs(self):
        self.assertEqual(self.st._laser_estop_addrs[1], frozenset({10, 11, 12, 13}))
        self.assertEqual(self.st._laser_fids, frozenset({7}))   # nur der Laser

    def test_estop_forces_laser_channels_dark(self):
        self.st.programmer = {7: {"laser_bank": 100, "gobo_wheel": 55},
                              9: {"intensity": 200}}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 100)        # Laser läuft
        self.assertEqual(self.live.get_channel(20), 200)        # PAR läuft

        self.st.set_laser_estop(True)
        self.st._render_frame(0.02)
        # Alle Laser-Kanäle hart auf 0 …
        for addr in (10, 11, 12, 13):
            self.assertEqual(self.live.get_channel(addr), 0)
        # … der PAR bleibt unberührt (NOT-AUS gilt nur dem Laser).
        self.assertEqual(self.live.get_channel(20), 200)

    def test_setting_laser_value_clears_latch(self):
        self.st.set_laser_estop(True)
        # Bewusster neuer Laser-Wert = „wieder an" → Latch löst.
        self.st.set_programmer_value(7, "laser_bank", 42)
        self.assertFalse(self.st.laser_estop_active)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 42)         # Laser wieder da

    def test_non_laser_value_keeps_latch(self):
        self.st.set_laser_estop(True)
        self.st.set_programmer_value(9, "intensity", 255)       # PAR, kein Laser
        self.assertTrue(self.st.laser_estop_active)             # Latch bleibt

    def test_estop_all_sets_latch(self):
        from src.core.laser.laser_output import LaserOutputManager
        lo = LaserOutputManager(self.st)
        lo.estop_all()
        self.assertTrue(self.st.laser_estop_active)


if __name__ == "__main__":
    unittest.main()
