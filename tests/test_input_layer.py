"""F-20: Art-Net/sACN-Eingang als deterministische Render-Schicht.

Der externe Eingang schreibt nicht mehr direkt ins Live-Universe (das ueberschrieb
der Per-Frame-Renderer auf gepatchten Kanaelen), sondern in ``state.input_layer``;
``_render_frame`` mischt ihn je Universe mit HTP/LTP/REPLACE. Mirror von
tests/test_iso_simple_desk.py (Fake-State ohne DB/Threads)."""
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
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.simple_desk = {}
    st.simple_desk_override = False             # SD aus -> nur Input-Schicht testen
    st.input_layer = {}
    st.input_merge_modes = {}
    st._input_lock = threading.RLock()
    st.playback_engine = None
    st.function_manager = _FM()
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st._patch_cache = [_Fx(1, 1, 10)]          # Adressen 10..13
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


class ApplyAndClearTest(_Base):
    def test_apply_stores_values_and_mode(self):
        self.st.apply_input_merge(1, bytes([0, 0, 0, 0, 0, 0, 0, 0, 0, 200]), "LTP")
        self.assertEqual(self.st.input_layer[1][10], 200)
        self.assertEqual(self.st.input_merge_modes[1], "LTP")

    def test_bad_mode_falls_back_htp(self):
        self.st.apply_input_merge(1, bytes([5]), "quatsch")
        self.assertEqual(self.st.input_merge_modes[1], "HTP")

    def test_clear_one_and_all(self):
        self.st.apply_input_merge(1, bytes([1]), "HTP")
        self.st.apply_input_merge(2, bytes([1]), "HTP")
        self.st.clear_input_merge(1)
        self.assertNotIn(1, self.st.input_layer)
        self.assertIn(2, self.st.input_layer)
        self.st.clear_input_merge()
        self.assertEqual(self.st.input_layer, {})
        self.assertEqual(self.st.input_merge_modes, {})


class RenderMergeTest(_Base):
    def test_htp_input_beats_lower_show(self):
        self.st.programmer = {1: {"intensity": 50}}     # Adr 10 = 50
        self.st.input_layer = {1: {10: 200}}
        self.st.input_merge_modes = {1: "HTP"}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)   # Input hoeher -> gewinnt

    def test_htp_show_beats_lower_input(self):
        self.st.programmer = {1: {"intensity": 200}}
        self.st.input_layer = {1: {10: 30}}
        self.st.input_merge_modes = {1: "HTP"}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)   # Show hoeher -> bleibt

    def test_replace_overwrites_show(self):
        self.st.programmer = {1: {"intensity": 200}}
        self.st.input_layer = {1: {10: 30}}
        self.st.input_merge_modes = {1: "REPLACE"}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 30)    # Input ersetzt

    def test_free_channel_committed_and_released(self):
        self.st.input_layer = {1: {300: 123}}
        self.st.input_merge_modes = {1: "HTP"}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(300), 123)  # freier Kanal committed
        self.st.clear_input_merge()
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(300), 0)    # freigegeben, kein Zombie

    def test_empty_input_no_effect(self):
        self.st.programmer = {1: {"intensity": 200}}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)   # 0 Regression ohne Input

    def test_simple_desk_wins_over_input(self):
        # Simple-Desk-Override (4c) liegt ueber der Input-Schicht (4b-Input).
        self.st.simple_desk_override = True
        self.st.set_simple_desk_channel(1, 10, 50)
        self.st.input_layer = {1: {10: 200}}
        self.st.input_merge_modes = {1: "HTP"}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 50)    # SD gewinnt oben


if __name__ == "__main__":
    unittest.main()
