"""A3D-18: Entfernen/Umadressieren eines Fixtures nullt seine bisherigen
DMX-Adressen im Live-Universe (sonst bleibt der letzte committete Wert als
Zombie-Kanal stehen — bei Dimmer/Shutter/Beam sicht-/sicherheitsrelevant).

_render_frame committet (Schritt 5) nur noch die NEUEN _commit_spans, und
_release_engine_extra erfasst ausschliesslich ungepatchte Roh-Kanaele. Eine alte
Fixture-Adresse ist keins von beidem -> _rebuild_render_plan muss sie freigeben.
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
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4
    protocol = ""

    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = ""


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


_CH = {5: [_Ch("intensity", 1), _Ch("color_r", 2),
           _Ch("color_g", 3), _Ch("color_b", 4)]}


def _make_state(patch):
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = list(patch)
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st._rebuild_render_plan()
    return st


class ZombieChannelReleaseTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CH[fx.fid]

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_render_plan_collects_patched_addrs(self):
        st = _make_state([_Fx(5, 1, 10)])
        self.assertEqual(st._patched_set[1], frozenset({10, 11, 12, 13}))

    def test_removing_fixture_zeros_old_addresses(self):
        st = _make_state([_Fx(5, 1, 10)])
        live = st.universes[1]
        for a in (10, 11, 12, 13):                 # committeter Live-Stand
            live.set_channel(a, 200)
        st._patch_cache = []                        # Fixture entfernt
        st._rebuild_render_plan()
        for a in (10, 11, 12, 13):
            self.assertEqual(live.get_channel(a), 0, f"addr {a} blieb Zombie")

    def test_readdressing_releases_only_vacated_addresses(self):
        st = _make_state([_Fx(5, 1, 10)])           # belegt 10..13
        live = st.universes[1]
        for a in (10, 11, 12, 13):
            live.set_channel(a, 200)
        st._patch_cache = [_Fx(5, 1, 12)]           # verschoben -> belegt 12..15
        st._rebuild_render_plan()
        self.assertEqual(live.get_channel(10), 0)   # verlassen -> frei
        self.assertEqual(live.get_channel(11), 0)   # verlassen -> frei
        self.assertEqual(live.get_channel(12), 200)  # weiter gepatcht -> unberuehrt
        self.assertEqual(live.get_channel(13), 200)  # weiter gepatcht -> unberuehrt

    def test_first_build_has_nothing_to_release(self):
        # Kein _patched_set vor dem ersten Rebuild -> kein Crash, nichts genullt.
        st = _make_state([_Fx(5, 1, 10)])
        self.assertEqual(st._patched_set[1], frozenset({10, 11, 12, 13}))

    def test_pending_release_beats_stale_render_commit(self):
        # A3D-18-Review-Haertung: ein nachlaufender Alt-Plan-Commit darf die
        # freigegebene Adresse nicht dauerhaft wieder auferstehen lassen — der
        # naechste Render-Frame nullt sie via _pending_release final nach.
        st = _make_state([_Fx(5, 1, 10)])
        live = st.universes[1]
        for a in (10, 11, 12, 13):
            live.set_channel(a, 200)
        st._patch_cache = []
        st._rebuild_render_plan()
        for a in (10, 11, 12, 13):
            self.assertEqual(live.get_channel(a), 0)        # sofort genullt
        self.assertEqual(st._pending_release.get(1), {10, 11, 12, 13})
        # Simuliere den nachlaufenden Alt-Plan-Commit (stale Snapshot).
        for a in (10, 11, 12, 13):
            live.set_channel(a, 200)
        st._render_frame(0.02)
        for a in (10, 11, 12, 13):
            self.assertEqual(live.get_channel(a), 0, f"addr {a} nicht final genullt")
        self.assertNotIn(1, st._pending_release)            # konsumiert (pop)


if __name__ == "__main__":
    unittest.main()
