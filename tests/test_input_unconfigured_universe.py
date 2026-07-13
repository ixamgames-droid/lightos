"""NET-07: Merge in ein NICHT als Output gepatchtes ``out_universe`` wird vom
Renderer still verworfen (``scratch`` wird nur aus ``self.universes`` gebaut, also
``scratch.get(univ) is None -> continue``) — die UI zeigt trotzdem "Aktiv".

``apply_input_merge`` fuehrt jetzt ``input_unconfigured[out_univ]`` (Zaehler:
dropped-because-unconfigured), den die Status-Abfrage lesen kann. Der Erfolgsfall
(gepatchtes Ziel) bleibt unveraendert. Fake-State-Muster wie test_input_layer.py."""
import os
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.sync import get_sync


class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4

    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


def _make_state():
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}                # NUR Universe 1 gepatcht
    st.programmer = {}
    st.simple_desk = {}
    st.simple_desk_override = False
    st.input_layer = {}
    st.input_merge_modes = {}
    st.input_last_seen = {}
    st.input_unconfigured = {}                     # NET-07: Fehl-Ziel-Zaehler
    st._input_lock = threading.RLock()
    st.playback_engine = None
    st.function_manager = _FM()
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st._patch_cache = [_Fx(1, 1, 10)]              # Adressen 10..13
    st._prog_lock = threading.RLock()
    st._sd_lock = threading.RLock()
    st._callbacks = []
    st._ui_marshaller = None
    st._ui_thread_id = None
    st.sync = get_sync()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    return st


class _Base(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: [
            _Ch("intensity", 1, 0), _Ch("color_r", 2, 0),
            _Ch("color_g", 3, 0), _Ch("color_b", 4, 5),
        ]
        self.st = _make_state()
        self.st._rebuild_render_plan()
        self.live = self.st.universes[1]

    def tearDown(self):
        A.get_channels_for_patched = self._orig


class UnconfiguredTargetTest(_Base):
    def test_unconfigured_target_flagged_and_channels_dropped(self):
        # Universe 5 ist NICHT gepatcht -> der Renderer verwirft die Kanaele still.
        self.st.apply_input_merge(5, bytes([0] * 9 + [200]), "REPLACE")
        # Erkennbares Signal gesetzt (dropped-because-unconfigured):
        self.assertIn(5, self.st.input_unconfigured)
        self.assertGreaterEqual(self.st.input_unconfigured[5], 1)
        # Es entsteht kein Live-Universe 5 -> die Kanaele landen nirgends (nicht in
        # scratch, das nur aus self.universes gebaut wird).
        self.st._render_frame(0.02)                 # darf nicht crashen
        self.assertNotIn(5, self.st.universes)

    def test_counter_increments_per_frame(self):
        self.st.apply_input_merge(5, bytes([1]), "HTP")
        self.st.apply_input_merge(5, bytes([1]), "HTP")
        self.st.apply_input_merge(5, bytes([1]), "HTP")
        self.assertEqual(self.st.input_unconfigured[5], 3)

    def test_clear_removes_flag(self):
        self.st.apply_input_merge(5, bytes([1]), "HTP")
        self.assertIn(5, self.st.input_unconfigured)
        self.st.clear_input_merge(5)
        self.assertNotIn(5, self.st.input_unconfigured)

    def test_flag_cleared_when_target_later_patched(self):
        self.st.apply_input_merge(5, bytes([1]), "HTP")
        self.assertIn(5, self.st.input_unconfigured)
        # Universe 5 wird nachtraeglich als Output konfiguriert:
        self.st.universes[5] = Universe(5)
        self.st.apply_input_merge(5, bytes([1]), "HTP")
        self.assertNotIn(5, self.st.input_unconfigured)


class ConfiguredTargetUnchangedTest(_Base):
    def test_configured_target_not_flagged(self):
        # Universe 1 IST gepatcht -> kein Fehl-Flag, Merge wirkt normal.
        self.st.apply_input_merge(1, bytes([0] * 9 + [200]), "REPLACE")
        self.assertNotIn(1, self.st.input_unconfigured)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)   # Erfolgsfall unveraendert

    def test_configured_target_stores_values_and_mode(self):
        self.st.apply_input_merge(1, bytes([0] * 9 + [123]), "LTP")
        self.assertEqual(self.st.input_layer[1][10], 123)
        self.assertEqual(self.st.input_merge_modes[1], "LTP")
        self.assertEqual(self.st.input_unconfigured, {})


if __name__ == "__main__":
    unittest.main()
