"""Feature-Dimmer-Master (F-26): per-Slot multiplikativer Master, der die
Helligkeit (bzw. gewaehlte Feature-Kanaele) einer Fixture-Menge effekt-UNABHAENGIG
skaliert — Render-Schritt 4b², NACH allen Effekten/Programmer.

Geprueft wird das Verhalten am echten _render_frame (wie test_dimmer_master.py):
  * "Intensity"-Feature dimmt den echten Dimmer-Kanal,
  * dimmt eine reine RGB-Fixture ueber den Farb-Fallback (inten_addrs),
  * "Color"-Feature skaliert NUR Farbkanaele, nicht den Dimmer,
  * Shutter/Strobe wird ueber "Intensity" NICHT mitgedimmt (wie Grand Master),
  * mehrere Slots stapeln multiplikativ (Produkt) + komponieren mit dem globalen
    Submaster, und ein Slot hat Identitaet (Ersetzen statt Stapeln),
  * level>=1.0 bzw. keine fids entfernt den Slot (no-op).
"""
import os
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState, FeatureDimmer
from src.core.dmx.universe import Universe
from src.core.dmx.output_manager import OutputManager


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num


class _Fx:
    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


class _FM:
    """Fake-FunctionManager: schreibt feste {addr: wert} in Universe 1."""
    def __init__(self, writes):
        self.writes = dict(writes)

    def tick(self, universes, patch_cache, dt):
        if 1 in universes:
            for a, v in self.writes.items():
                universes[1].set_channel(a, v)


def _state(fixtures, writes):
    """fixtures: dict fid -> (address, [(attr, channel_number), ...]).
    writes:   {abs_addr: value} — der Effekt schreibt sie jeden Frame.
    implicit_brightness=False -> keine 4a²-Grundhelligkeit (deterministische Tests)."""
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM(writes)
    fix_index = {}
    patch = []
    for fid, (addr, chspec) in fixtures.items():
        fx = _Fx(fid, 1, addr)
        chans = [_Ch(a, n) for (a, n) in chspec]
        fix_index[fid] = (fx, chans)
        patch.append(fx)
    st._fix_index = fix_index
    st._default_frame = {1: bytes(512)}
    st._commit_spans = {1: [(1, 512)]}
    st._patched_set = {1: frozenset(range(1, 513))}
    st._engine_extra_prev = {}
    st._patch_cache = patch
    st.implicit_brightness = False
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    st.feature_dimmers = {}
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    return st


def _v(st, addr):
    return st.universes[1].get_channel(addr)


# Ein PAR mit echtem Dimmer + RGB an Adresse 1 (intensity@1, R@2, G@3, B@4).
_PAR = {1: (1, [("intensity", 1), ("color_r", 2), ("color_g", 3), ("color_b", 4)])}
# Reine RGB-Bar ohne Dimmer (R@1, G@2, B@3).
_RGB = {1: (1, [("color_r", 1), ("color_g", 2), ("color_b", 3)])}
# Fixture mit Dimmer + Shutter (intensity@1, shutter@2).
_DIM_SHUT = {1: (1, [("intensity", 1), ("shutter", 2)])}


class FeatureDimmerRenderTest(unittest.TestCase):

    def test_intensity_dims_real_dimmer(self):
        st = _state(_PAR, {1: 200})
        st.set_feature_dimmer("s", [1], None, 0.5)   # Default-Feature = Intensity
        st._render_frame(0.02)
        self.assertAlmostEqual(_v(st, 1), 100, delta=1)

    def test_intensity_dims_pure_rgb_via_fallback(self):
        # Reine RGB ohne Dimmer: inten_addrs faellt auf die Farbkanaele zurueck →
        # der Helligkeits-Master dimmt sie (genau wie der globale Submaster).
        st = _state(_RGB, {1: 200, 2: 100, 3: 50})
        st.set_feature_dimmer("s", [1], None, 0.5)
        st._render_frame(0.02)
        self.assertAlmostEqual(_v(st, 1), 100, delta=1)
        self.assertAlmostEqual(_v(st, 2), 50, delta=1)
        self.assertAlmostEqual(_v(st, 3), 25, delta=1)

    def test_color_feature_scales_color_not_intensity(self):
        st = _state(_PAR, {1: 200, 2: 200})            # Dimmer + Rot getrieben
        st.set_feature_dimmer("s", [1], {"Color"}, 0.5)
        st._render_frame(0.02)
        self.assertAlmostEqual(_v(st, 1), 200, delta=1)  # Dimmer unberuehrt
        self.assertAlmostEqual(_v(st, 2), 100, delta=1)  # Rot halbiert

    def test_shutter_not_dimmed_by_intensity(self):
        st = _state(_DIM_SHUT, {1: 200, 2: 200})
        st.set_feature_dimmer("s", [1], None, 0.5)       # Intensity
        st._render_frame(0.02)
        self.assertAlmostEqual(_v(st, 1), 100, delta=1)  # Dimmer halbiert
        self.assertEqual(_v(st, 2), 200)                 # Shutter unangetastet

    def test_slots_stack_multiplicatively(self):
        st = _state(_PAR, {1: 200})
        st.set_feature_dimmer("a", [1], None, 0.5)
        st.set_feature_dimmer("b", [1], None, 0.5)
        st._render_frame(0.02)
        self.assertAlmostEqual(_v(st, 1), 50, delta=1)   # 200 * 0.5 * 0.5

    def test_composes_with_global_submaster(self):
        st = _state(_PAR, {1: 200})
        st.output_manager = OutputManager()
        st.output_manager.set_submaster(0, 0.5)          # globaler Submaster (4b)
        st.set_feature_dimmer("s", [1], None, 0.5)       # Feature-Dimmer (4b²)
        st._render_frame(0.02)
        self.assertAlmostEqual(_v(st, 1), 50, delta=1)   # 200 * 0.5 * 0.5

    def test_slot_has_identity_replace_not_stack(self):
        st = _state(_PAR, {1: 200})
        st.set_feature_dimmer("s", [1], None, 0.5)
        st.set_feature_dimmer("s", [1], None, 0.25)      # ersetzt denselben Slot
        self.assertEqual(len(st.feature_dimmers), 1)
        st._render_frame(0.02)
        self.assertAlmostEqual(_v(st, 1), 50, delta=1)   # 200 * 0.25 (nicht *0.5*0.25)

    def test_full_level_removes_slot(self):
        st = _state(_PAR, {1: 200})
        st.set_feature_dimmer("s", [1], None, 1.0)
        self.assertNotIn("s", st.feature_dimmers)
        st._render_frame(0.02)
        self.assertEqual(_v(st, 1), 200)

    def test_no_fids_removes_slot(self):
        st = _state(_PAR, {1: 200})
        st.set_feature_dimmer("s", [], None, 0.5)
        self.assertNotIn("s", st.feature_dimmers)
        st._render_frame(0.02)
        self.assertEqual(_v(st, 1), 200)


class SetFeatureDimmerApiTest(unittest.TestCase):
    """API-Verhalten von set_feature_dimmer ohne Render."""

    def _st(self):
        st = AppState.__new__(AppState)
        st.feature_dimmers = {}
        return st

    def test_stores_featuredimmer(self):
        st = self._st()
        st.set_feature_dimmer("s", [1, 2], {"Intensity", "Color"}, 0.4)
        fd = st.feature_dimmers["s"]
        self.assertIsInstance(fd, FeatureDimmer)
        self.assertEqual(fd.fids, frozenset({1, 2}))
        self.assertEqual(fd.features, frozenset({"Intensity", "Color"}))
        self.assertAlmostEqual(fd.level, 0.4)

    def test_level_clamped(self):
        st = self._st()
        st.set_feature_dimmer("s", [1], None, -3.0)   # < 0 -> 0.0 (gespeichert)
        self.assertAlmostEqual(st.feature_dimmers["s"].level, 0.0)
        st.set_feature_dimmer("t", [1], None, 5.0)    # > 1 -> 1.0 -> Slot entfaellt
        self.assertNotIn("t", st.feature_dimmers)

    def test_invalid_fids_skipped(self):
        st = self._st()
        st.set_feature_dimmer("s", [1, "x", None, 3], None, 0.5)
        self.assertEqual(st.feature_dimmers["s"].fids, frozenset({1, 3}))

    def test_clear(self):
        st = self._st()
        st.set_feature_dimmer("s", [1], None, 0.5)
        st.clear_feature_dimmers()
        self.assertEqual(st.feature_dimmers, {})


if __name__ == "__main__":
    unittest.main()
