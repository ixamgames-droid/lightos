"""Regressionstests fuer den zentralen Per-Frame-Renderer (AppState._render_frame).

Deckt C6/C7 ab: Per-Frame-Clear (haengende Werte), Layer-Reihenfolge
(Default->Funktionen->Executoren->Programmer, LTP), Erhalt nicht gepatchter
Roh-Kanaele und korrektes Schreiben/Freigeben roher Funktions-Ausgaben.
"""
import os
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

    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


class _FM:
    """Fake-FunctionManager: schreibt optional einen Rohkanal."""
    def __init__(self):
        self.raw_addr = None
        self.raw_val = 0

    def tick(self, universes, patch_cache, dt):
        if self.raw_addr is not None and 1 in universes:
            universes[1].set_channel(self.raw_addr, self.raw_val)


def _make_state():
    st = AppState.__new__(AppState)        # ohne __init__ (keine DB/Threads)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st._patch_cache = [_Fx(1, 1, 10)]      # Adressen 10..13
    import threading as _t, types as _ty
    st._prog_lock = _t.RLock()             # set_programmer_value/_render_frame
    st.output_manager = _ty.SimpleNamespace(set_gm_address_mask=lambda m: None)
    return st


class RenderFrameTest(unittest.TestCase):
    def setUp(self):
        # Kanalliste fuer den Fake-Patch: intensity, r, g, b (b Default 5)
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

    def test_render_plan(self):
        self.assertEqual(self.st._commit_spans[1], [(10, 4)])
        self.assertEqual(list(self.st._default_frame[1][9:13]), [0, 0, 0, 5])

    def test_defaults_and_raw_preserved(self):
        self.live.set_channel(20, 222)         # nicht gepatchter Rohkanal
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 0)
        self.assertEqual(self.live.get_channel(13), 5)   # Default honoriert
        self.assertEqual(self.live.get_channel(20), 222)  # Roh erhalten

    def test_programmer_override(self):
        self.st.programmer = {1: {"intensity": 200, "color_r": 128}}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)
        self.assertEqual(self.live.get_channel(11), 128)
        self.assertEqual(self.live.get_channel(13), 5)

    def test_per_frame_clear_releases_value(self):
        self.st.programmer = {1: {"intensity": 200}}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)
        self.st.programmer = {}                # Wert weg -> naechster Frame Default
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 0)

    def test_programmer_beats_executor(self):
        class _PE:
            def compute_merged(self):
                return {1: {"intensity": 100, "color_g": 77}}
        self.st.playback_engine = _PE()
        self.st.programmer = {1: {"intensity": 200}}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)   # Programmer > Executor
        self.assertEqual(self.live.get_channel(12), 77)    # Executor-Layer

    def test_function_raw_channel_write_and_release(self):
        self.live.set_channel(80, 99)          # fremder Roh-Schreiber
        self.st.function_manager.raw_addr = 50
        self.st.function_manager.raw_val = 200
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(50), 200)   # Script-Rohkanal committed
        self.assertEqual(self.live.get_channel(80), 99)    # fremder Roh erhalten
        self.st.function_manager.raw_addr = None           # Funktion stoppt
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(50), 0)     # freigegeben
        self.assertEqual(self.live.get_channel(80), 99)    # weiterhin erhalten


class BaseLevelsTest(unittest.TestCase):
    """Sichert den Layer-Fix vom 2026-06-02 ab: Basis-Helligkeit macht eine
    reine Farbe (color-only) sofort sichtbar, ein Dimmer-Effekt UEBERSCHREIBT die
    Basis und kann bis 0 dunkeln (kein 'Lauflicht bleibt hell')."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: [
            _Ch("intensity", 1, 0), _Ch("color_r", 2, 0),
            _Ch("color_g", 3, 0), _Ch("color_b", 4, 0),
        ]
        self.st = _make_state()
        self.st.base_levels = {1: {"intensity": 255}}   # PAR "scharf"
        self.st.submaster_level = 1.0
        self.st.fixture_dimmers = {}
        self.st._rebuild_render_plan()
        self.live = self.st.universes[1]

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_base_in_default_frame(self):
        # Intensitaet (Kanal 1 -> Adresse 10) traegt die Basis 255.
        self.assertEqual(self.st._default_frame[1][9], 255)

    def test_color_only_instant_light(self):
        # Nur Farbe im Programmer (keine Intensitaet) -> Basis macht hell.
        self.st.programmer = {1: {"color_r": 255}}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 255)   # Intensitaet aus Basis
        self.assertEqual(self.live.get_channel(11), 255)   # Farbe gesetzt

    def test_effect_overrides_base_to_zero(self):
        # Ein Effekt, der die Intensitaet auf 0 zieht, gewinnt ueber die Basis —
        # color-only Programmer leuchtet sie NICHT wieder hoch (der fruehere Bug).
        self.st.programmer = {1: {"color_r": 255}}
        self.st.function_manager.raw_addr = 10   # Intensitaets-Adresse
        self.st.function_manager.raw_val = 0
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 0)

    def test_submaster_dims_base_to_zero(self):
        self.st.programmer = {1: {"color_r": 255}}
        self.st.submaster_level = 0.0
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 0)


if __name__ == "__main__":
    unittest.main()
