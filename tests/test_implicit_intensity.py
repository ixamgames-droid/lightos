"""Implizite Grundhelligkeit (4a²): „Farbe heisst sichtbar".

Ein Fixture mit eigenem Dimmer-Kanal, das gefaerbt ist (Programmer ODER Effekt),
dessen Dimmer aber von NICHTS getrieben wird, soll im _render_frame automatisch
auf voll gehen — damit reine Farb-Effekte/Matrizen leuchten, ohne dass der
Master-/Programmer-Dimmer manuell hochgezogen werden muss.

Wichtige Gegenprobe: ein echter Dimmer-Effekt (auch im Nulldurchgang, Wert 0)
muss seinen Vorrang behalten und darf NICHT aufgehellt werden (sonst Strobe kaputt).
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
    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


class _FM:
    """Fake-FunctionManager: schreibt optional einen Kanal (Effekt-Simulation)."""
    def __init__(self):
        self.writes: dict[int, int] = {}   # {addr: value}

    def tick(self, universes, patch_cache, dt):
        u = universes.get(1)
        if u is None:
            return
        for addr, val in self.writes.items():
            u.set_channel(addr, val)


def _make_state(channels):
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    fx = _Fx(1, 1, 10)                       # Adressen 10..
    st._patch_cache = [fx]
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    import threading as _t, types as _ty
    st._prog_lock = _t.RLock()
    st.output_manager = _ty.SimpleNamespace(set_gm_address_mask=lambda m: None)
    A.get_channels_for_patched = lambda f: channels
    st._rebuild_render_plan()
    return st


# Fixture MIT Dimmer-Kanal: intensity@1(=10), R@2(=11), G@3(=12), B@4(=13)
_DIMMED = [_Ch("intensity", 1, 0), _Ch("color_r", 2, 0),
           _Ch("color_g", 3, 0), _Ch("color_b", 4, 0)]
# Reines RGB-Fixture OHNE Dimmer: R@1(=10), G@2(=11), B@3(=12)
_RGB = [_Ch("color_r", 1, 0), _Ch("color_g", 2, 0), _Ch("color_b", 3, 0)]


class ImplicitIntensityTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _val(self, st, addr):
        return st.universes[1].get_channel(addr)

    # ── Kernfall: Farbe im Programmer ohne Dimmer → leuchtet trotzdem ──────────
    def test_programmer_color_only_lights_up(self):
        st = _make_state(_DIMMED)
        st.programmer = {1: {"color_r": 200}}
        st._render_frame(0.02)
        self.assertEqual(self._val(st, 10), 255)   # Dimmer implizit voll
        self.assertEqual(self._val(st, 11), 200)   # Farbe gesetzt

    # ── Farb-Effekt/Matrix (color-only) ohne Programmer → leuchtet ────────────
    def test_color_effect_only_lights_up(self):
        st = _make_state(_DIMMED)
        st.function_manager.writes = {11: 180}     # Matrix faerbt R, fasst Dimmer NICHT an
        st._render_frame(0.02)
        self.assertEqual(self._val(st, 10), 255)   # Dimmer implizit voll
        self.assertEqual(self._val(st, 11), 180)

    # ── GEGENPROBE: Dimmer-Effekt im Nulldurchgang bleibt dunkel ──────────────
    def test_dimmer_effect_at_zero_stays_dark(self):
        st = _make_state(_DIMMED)
        # Effekt faerbt R UND treibt den Dimmer — gerade auf 0 (Strobe-Aus-Phase).
        st.function_manager.writes = {11: 180, 10: 0}
        st.programmer = {1: {"color_r": 200}}
        st._render_frame(0.02)
        # Dimmer wird vom Effekt „besessen" (Write-Log) → NICHT aufgehellt.
        self.assertEqual(self._val(st, 10), 0)

    # ── Programmer setzt Dimmer explizit auf 0 → respektiert ──────────────────
    def test_explicit_programmer_zero_dimmer_respected(self):
        st = _make_state(_DIMMED)
        st.programmer = {1: {"color_r": 200, "intensity": 0}}
        st._render_frame(0.02)
        self.assertEqual(self._val(st, 10), 0)

    # ── Reines RGB-Fixture (kein Dimmer-Kanal) bleibt unberuehrt ──────────────
    def test_pure_rgb_fixture_unaffected(self):
        st = _make_state(_RGB)
        st.programmer = {1: {"color_r": 120}}
        st._render_frame(0.02)
        self.assertEqual(self._val(st, 10), 120)   # Farbe = Helligkeit, wie gehabt
        self.assertEqual(self._val(st, 11), 0)
        self.assertEqual(self._val(st, 12), 0)

    # ── Submaster skaliert das implizite Voll ─────────────────────────────────
    def test_submaster_scales_implicit_full(self):
        st = _make_state(_DIMMED)
        st.programmer = {1: {"color_r": 200}}
        st.submaster_level = 0.5
        st._render_frame(0.02)
        self.assertAlmostEqual(self._val(st, 10), 127, delta=2)   # 255 * 0.5

    # ── Keine Farbe → bleibt dunkel (kein „immer an") ─────────────────────────
    def test_no_color_stays_dark(self):
        st = _make_state(_DIMMED)
        st.programmer = {1: {"pan": 100}}          # nur Position, keine Farbe
        st._render_frame(0.02)
        self.assertEqual(self._val(st, 10), 0)

    # ── implicit_brightness=False: strikte Trennung Farbe/Dimmer ──────────────
    def test_flag_off_color_only_stays_dark(self):
        st = _make_state(_DIMMED)
        st.implicit_brightness = False             # Farb-Seite rührt den Dimmer nicht an
        st.programmer = {1: {"color_r": 200}}
        st._render_frame(0.02)
        self.assertEqual(self._val(st, 10), 0)     # Dimmer bleibt dunkel (kein implizites Voll)
        self.assertEqual(self._val(st, 11), 200)   # Farbe ist trotzdem gesetzt

    def test_flag_off_dimmer_effect_still_lights(self):
        st = _make_state(_DIMMED)
        st.implicit_brightness = False
        st.function_manager.writes = {11: 180, 10: 220}   # Dimmer-Effekt treibt Intensitaet
        st._render_frame(0.02)
        self.assertEqual(self._val(st, 10), 220)   # Dimmer-Effekt hellt auf
        self.assertEqual(self._val(st, 11), 180)


if __name__ == "__main__":
    unittest.main()
