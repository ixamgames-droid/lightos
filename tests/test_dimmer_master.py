"""EE-02: Multiplikativer Dimmer-Master ueber dem Effekt-Layer.

Deckt die drei Dimmer-Quellen ab, die laufende Effekte herunterregeln sollen:
  - globaler Submaster (VC-Fader)
  - Gruppen-/Fixture-Dimmer (state.fixture_dimmers)
  - Programmer-Dimmer multipliziert den Effekt (statt LTP-Ersatz), wenn ein
    Effekt die Intensitaet treibt; ohne Effekt bleibt der Programmer absolut.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.dmx.output_manager import OutputManager


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
    """Fake-FunctionManager: simuliert einen Effekt, der die Intensitaet (Addr 1)
    auf 200 schreibt — sofern aktiv."""
    def __init__(self, value=200, active=True):
        self.value = value
        self.active = active

    def tick(self, universes, patch_cache, dt):
        if self.active and 1 in universes:
            universes[1].set_channel(1, self.value)


def _make_state(effect_active=True):
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM(active=effect_active)
    fx = _Fx(1, 1, 1)
    chans = [_Ch("intensity", 1, 0)]
    st._fix_index = {1: (fx, chans)}
    st._default_frame = {1: bytes(512)}
    st._commit_spans = {1: [(1, 1)]}
    st._patched_set = {1: frozenset({1})}
    st._engine_extra_prev = {}
    st._patch_cache = [fx]
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    return st


class TestDimmerMaster(unittest.TestCase):
    def _val(self, st):
        return st.universes[1].get_channel(1)

    def test_effect_full_without_dimmer(self):
        st = _make_state()
        st._render_frame(0.02)
        self.assertEqual(self._val(st), 200)

    def test_submaster_scales_effect(self):
        st = _make_state()
        st.output_manager = OutputManager()
        st.output_manager.set_submaster(0, 0.5)
        st._render_frame(0.02)
        self.assertAlmostEqual(self._val(st), 100, delta=1)

    def test_fixture_dimmer_scales_effect(self):
        st = _make_state()
        st.set_fixture_dimmer(1, 0.25)
        st._render_frame(0.02)
        self.assertAlmostEqual(self._val(st), 50, delta=1)

    def test_group_dimmer_api(self):
        st = _make_state()
        st.set_group_dimmer([1], 0.5)
        st._render_frame(0.02)
        self.assertAlmostEqual(self._val(st), 100, delta=1)

    def test_programmer_dimmer_multiplies_running_effect(self):
        st = _make_state()
        st.programmer = {1: {"intensity": 128}}
        st._render_frame(0.02)
        # Effekt 200 * (128/255) ≈ 100  — NICHT hart auf 128 ersetzt.
        self.assertAlmostEqual(self._val(st), 100, delta=2)

    def test_programmer_dimmer_absolute_without_effect(self):
        st = _make_state(effect_active=False)
        st.programmer = {1: {"intensity": 128}}
        st._render_frame(0.02)
        # Kein Effekt -> Programmer bleibt absolut (normales Programmieren).
        self.assertEqual(self._val(st), 128)

    def test_full_dimmer_is_noop(self):
        st = _make_state()
        st.set_fixture_dimmer(1, 1.0)   # entfernt Eintrag wieder
        self.assertNotIn(1, st.fixture_dimmers)
        st._render_frame(0.02)
        self.assertEqual(self._val(st), 200)


if __name__ == "__main__":
    unittest.main()
