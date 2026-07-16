"""A3D-01: Laser-NOT-AUS darf nicht durch einen Channel-Modifier ausgehebelt werden.

Der Renderer zwingt bei aktivem `laser_estop_active` alle Laser-Adressen im
Universe-Puffer auf 0 (UXT-12). Der OutputManager las diesen Puffer aber und wandte
DANACH die Channel-Modifier an — ein auf einer Laser-Adresse konfigurierter
Modifier machte aus der erzwungenen 0 wieder 255 (INVERSE) bzw. `range_min`
(Range-Lock), sodass der DMX-Laser trotz gedrücktem NOT-AUS weiter emittierte.

Fix: der OutputManager erzwingt die verriegelten Laser-Adressen FINAL (nach
Modifier + Grand-Master + Blackout) auf 0. AppState pusht die Maske bei jeder
Änderung von `laser_estop_active` bzw. der Laser-Adressen.
"""
import os
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.output_manager import OutputManager
from src.core.dmx.universe import Universe
from src.core.engine.channel_modifier import (
    ChannelModifier, CurveType, get_modifier_manager,
)


class LaserEstopModifierOutputTest(unittest.TestCase):
    """OutputManager-Ebene: die eigentliche A3D-01-Kette (Modifier vs. Estop)."""

    def setUp(self):
        self.om = OutputManager()
        self.u = self.om.add_universe(1)
        self.mgr = get_modifier_manager()
        self.mgr.clear()

    def tearDown(self):
        self.mgr.clear()

    def _out(self, addr):
        """Das gesendete/angezeigte Byte an DMX-Adresse `addr` (1-basiert)."""
        return self.om._display_frame[1][addr - 1]

    def test_inverse_modifier_reproduces_and_fix_forces_zero(self):
        # Renderer hat die Laser-Adresse bereits dunkel gestellt.
        self.u.set_channel(10, 0)
        self.mgr.add(ChannelModifier(universe=1, address=10, curve=CurveType.INVERSE))

        # OHNE Estop-Maske: der Modifier macht aus 0 -> 255 (Bug-Reproduktion,
        # beweist zugleich, dass der Modifier im Sendepfad wirklich greift).
        self.om._send_all()
        self.assertEqual(self._out(10), 255)

        # MIT Estop-Maske: die Laser-Adresse wird final auf 0 gezwungen.
        self.om.set_laser_estop_mask({1: frozenset({10})})
        self.om._send_all()
        self.assertEqual(self._out(10), 0)

    def test_range_lock_modifier_forced_to_zero(self):
        self.u.set_channel(11, 0)
        # Range-Lock: apply(0) -> range_min (hier 120), also nonzero.
        self.mgr.add(ChannelModifier(universe=1, address=11, range_min=120, range_max=255))

        self.om._send_all()
        self.assertEqual(self._out(11), 120)          # Bug-Reproduktion

        self.om.set_laser_estop_mask({1: frozenset({11})})
        self.om._send_all()
        self.assertEqual(self._out(11), 0)

    def test_empty_mask_is_noop(self):
        self.u.set_channel(10, 0)
        self.mgr.add(ChannelModifier(universe=1, address=10, curve=CurveType.INVERSE))
        self.om.set_laser_estop_mask({})               # NOT-AUS inaktiv
        self.om._send_all()
        self.assertEqual(self._out(10), 255)

    def test_only_masked_addresses_forced(self):
        # Zwei INVERSE-Modifier: 10 (Laser, maskiert) und 20 (kein Laser).
        self.u.set_channel(10, 0)
        self.u.set_channel(20, 0)
        self.mgr.add(ChannelModifier(universe=1, address=10, curve=CurveType.INVERSE))
        self.mgr.add(ChannelModifier(universe=1, address=20, curve=CurveType.INVERSE))
        self.om.set_laser_estop_mask({1: frozenset({10})})
        self.om._send_all()
        self.assertEqual(self._out(10), 0)             # Laser: hart dunkel
        self.assertEqual(self._out(20), 255)           # Nicht-Laser: unberührt

    def test_estop_beats_grand_master(self):
        # Auch mit Grand-Master < 100 % (skaliert 255 -> nonzero) muss der Estop 0
        # erzwingen — er läuft final NACH dem GM-Schritt.
        self.u.set_channel(10, 0)
        self.mgr.add(ChannelModifier(universe=1, address=10, curve=CurveType.INVERSE))
        self.om.grand_master = 0.5
        self.om.set_laser_estop_mask({1: frozenset({10})})
        self.om._send_all()
        self.assertEqual(self._out(10), 0)

    def test_estop_beats_blackout_state_untouched(self):
        # Blackout nullt ohnehin alles; die Estop-Maske darf das nicht stören.
        self.u.set_channel(10, 0)
        self.mgr.add(ChannelModifier(universe=1, address=10, curve=CurveType.INVERSE))
        self.om.set_blackout(True)
        self.om.set_laser_estop_mask({1: frozenset({10})})
        self.om._send_all()
        self.assertEqual(self._out(10), 0)


# ── AppState-Integration: pusht die Maske am OutputManager korrekt ──────────────

class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4
    protocol = ""

    def __init__(self, fid, universe, address, ftype=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = ftype


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


_LASER = _Fx(7, 1, 10, ftype="laser")
_PAR = _Fx(9, 1, 20)
_CHANNELS = {
    7: [_Ch("laser_bank", 1), _Ch("gobo_wheel", 2), _Ch("laser_x", 3), _Ch("shutter", 4)],
    9: [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3), _Ch("color_b", 4)],
}


class LaserEstopMaskPushTest(unittest.TestCase):
    """AppState schiebt die Estop-Maske an einen ECHTEN OutputManager."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANNELS[fx.fid]
        st = AppState.__new__(AppState)
        st.universes = {1: Universe(1)}
        st.programmer = {}
        st.playback_engine = None
        st.function_manager = _FM()
        st._patch_cache = [_LASER, _PAR]
        st._prog_lock = threading.RLock()
        st.output_manager = OutputManager()        # ECHT — set_laser_estop_mask real
        st.laser_estop_active = False
        st._laser_estop_addrs = {}
        st._laser_fids = frozenset()
        st.base_levels = {}
        st._engine_extra_prev = {}
        st._suppress_emits = True
        st._rebuild_render_plan()
        self.st = st
        self.om = st.output_manager

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_mask_empty_until_estop(self):
        self.assertEqual(self.om._laser_estop_mask, {})

    def test_set_estop_pushes_laser_addrs(self):
        self.st.set_laser_estop(True)
        self.assertEqual(self.om._laser_estop_mask, {1: frozenset({10, 11, 12, 13})})

    def test_laser_value_clears_mask(self):
        self.st.set_laser_estop(True)
        self.st.set_programmer_value(7, "laser_bank", 42)   # bewusst "wieder an"
        self.assertFalse(self.st.laser_estop_active)
        self.assertEqual(self.om._laser_estop_mask, {})

    def test_non_laser_value_keeps_mask(self):
        self.st.set_laser_estop(True)
        self.st.set_programmer_value(9, "intensity", 255)   # PAR, kein Laser
        self.assertTrue(self.st.laser_estop_active)
        self.assertEqual(self.om._laser_estop_mask, {1: frozenset({10, 11, 12, 13})})

    def test_rebuild_while_active_keeps_mask(self):
        self.st.set_laser_estop(True)
        self.st._rebuild_render_plan()
        self.assertEqual(self.om._laser_estop_mask, {1: frozenset({10, 11, 12, 13})})


class LaserEstopEndToEndTest(unittest.TestCase):
    """Voller Pfad: echter Renderer (Schritt 4d nullt Puffer) + echter Sendepfad
    (Modifier hebt an, Estop-Maske nullt final) mit demselben gepatchten Laser."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANNELS[fx.fid]
        self.mgr = get_modifier_manager()
        self.mgr.clear()
        st = AppState.__new__(AppState)
        om = OutputManager()
        om.add_universe(1)
        st.universes = om.universes            # Renderer und Sender teilen dasselbe Universe
        st.output_manager = om
        st.programmer = {}
        st.playback_engine = None
        st.function_manager = _FM()
        st._patch_cache = [_LASER, _PAR]
        st._prog_lock = threading.RLock()
        st.laser_estop_active = False
        st._laser_estop_addrs = {}
        st._laser_fids = frozenset()
        st.base_levels = {}
        st._engine_extra_prev = {}
        st._suppress_emits = True
        st._rebuild_render_plan()
        self.st = st
        self.om = om

    def tearDown(self):
        A.get_channels_for_patched = self._orig
        self.mgr.clear()

    def _sent(self, addr):
        return self.om._display_frame[1][addr - 1]

    def test_render_plus_send_forces_laser_dark_through_inverse_modifier(self):
        # INVERSE-Modifier auf die Laser-Betriebsart-Adresse (10): apply(0) -> 255.
        self.mgr.add(ChannelModifier(universe=1, address=10, curve=CurveType.INVERSE))
        self.st.programmer = {7: {"laser_bank": 100}, 9: {"intensity": 200}}

        # Ohne NOT-AUS: Laser läuft, Modifier greift (Bug-Reproduktion am echten Pfad).
        self.st._render_frame(0.02)
        self.om._send_all()
        self.assertNotEqual(self._sent(10), 0)   # Laser emittiert (INVERSE(100)=155)
        self.assertEqual(self._sent(20), 200)    # PAR läuft

        # NOT-AUS: Renderer nullt Puffer (4d), Modifier hebt auf 255 an, Maske nullt final.
        self.st.set_laser_estop(True)
        self.st._render_frame(0.02)
        self.om._send_all()
        self.assertEqual(self._sent(10), 0)      # Laser trotz Modifier hart dunkel
        self.assertEqual(self._sent(20), 200)    # PAR unberührt (NOT-AUS gilt nur dem Laser)


if __name__ == "__main__":
    unittest.main()
