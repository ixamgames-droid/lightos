"""ENG-02: „Aktiver Programmer-Tab gewinnt" — Dimmer-Effekt (Matrix/EFX) vs.
per-Fixture Programmer-Intensity.

Reproduziert Davids Fall (Show 'test123'): eine Dimmer-Matrix treibt den
Intensitaets-Kanal zweier Moving Heads, deren Programmer beim Auswaehlen je
intensity=0 gespeichert hat. Simuliert wird der Effekt-Layer ueber einen
Fake-FunctionManager (schreibt direkt die Intensitaets-Adressen, wert-unabhaengig
ueber das Write-Log erfasst) — genau wie die echte Matrix im DIMMER-Style.

Erwartung:
  S1  Matrix sichtbar OHNE Master-Hochziehen (intensity=0 killt sie NICHT)
  S2  keine Invertierung bei hochgezogenem Master (gerade dunkle Pixel bleiben dunkel)
  Intensity-Tab + Fixture selektiert -> manuelle Intensitaet gewinnt absolut
  anderer Tab / Fixture nicht selektiert -> Effekt behaelt den Dimmer
Gegenprobe: ohne Effekt bleibt die Programmer-Intensitaet absolut (auch 0).
"""
import os
import threading as _t
import types as _ty
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
    """Fake-FunctionManager: schreibt vorgegebene {addr: value} als Effekt-Sim."""
    def __init__(self):
        self.writes: dict[int, int] = {}

    def tick(self, universes, patch_cache, dt):
        u = universes.get(1)
        if u is None:
            return
        for addr, val in self.writes.items():
            u.set_channel(addr, val)


# Zwei Moving Heads mit eigenem Dimmer-Kanal: MH 7 @ Adresse 10 (intensity=addr10),
# MH 8 @ Adresse 20 (intensity=addr20).
_FIXTURES = {
    7: (10, [_Ch("intensity", 1, 0)]),
    8: (20, [_Ch("intensity", 1, 0)]),
}
_INT7, _INT8 = 10, 20


def _make_state():
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = [_Fx(fid, 1, addr) for fid, (addr, _ch) in _FIXTURES.items()]
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    st.selected_fids = []
    st.programmer_focus = None
    st._prog_lock = _t.RLock()
    st.output_manager = _ty.SimpleNamespace(set_gm_address_mask=lambda m: None)
    _chans = {fid: ch for fid, (addr, ch) in _FIXTURES.items()}
    A.get_channels_for_patched = lambda f: _chans[f.fid]
    st._rebuild_render_plan()
    return st


class MatrixDimmerMasterTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _v(self, st, addr):
        return st.universes[1].get_channel(addr)

    # ── S1: Dimmer-Matrix sichtbar, obwohl Programmer-Intensity = 0 ───────────
    def test_s1_matrix_visible_with_programmer_zero(self):
        st = _make_state()
        st.function_manager.writes = {_INT7: 200, _INT8: 60}   # Chase laeuft
        st.programmer = {7: {"intensity": 0}, 8: {"intensity": 0}}  # auto-gesetzt
        st._render_frame(0.02)
        self.assertEqual(self._v(st, _INT7), 200)   # frueher: 0 (vom 0-Multiply gekillt)
        self.assertEqual(self._v(st, _INT8), 60)

    # ── S2: kein Invertieren, wenn der Master hochgezogen ist ─────────────────
    def test_s2_no_inversion_with_master_up(self):
        st = _make_state()
        # Chase: MH7 hell, MH8 gerade DUNKEL (Effekt schreibt 0 -> Write-Log besitzt
        # den Kanal trotzdem). Master auf beiden hochgezogen.
        st.function_manager.writes = {_INT7: 200, _INT8: 0}
        st.programmer = {7: {"intensity": 255}, 8: {"intensity": 255}}
        st._render_frame(0.02)
        self.assertEqual(self._v(st, _INT7), 200)
        self.assertEqual(self._v(st, _INT8), 0)     # frueher: 255 (Invertierung!)

    # ── Intensity-Tab + selektiert -> manuelle Intensitaet gewinnt absolut ────
    def test_intensity_tab_selected_overrides_effect(self):
        st = _make_state()
        st.function_manager.writes = {_INT7: 200}
        st.programmer = {7: {"intensity": 128}}
        st.selected_fids = [7]
        st.programmer_focus = "Intensity"
        st._render_frame(0.02)
        self.assertEqual(self._v(st, _INT7), 128)   # ersetzt den Effekt-Dimmer

    # ── Intensity-Tab, aber Fixture NICHT selektiert -> Effekt behaelt Dimmer ──
    def test_intensity_tab_unselected_keeps_effect(self):
        st = _make_state()
        st.function_manager.writes = {_INT7: 200}
        st.programmer = {7: {"intensity": 0}}
        st.selected_fids = [8]                       # man editiert MH8, nicht MH7
        st.programmer_focus = "Intensity"
        st._render_frame(0.02)
        self.assertEqual(self._v(st, _INT7), 200)    # MH7 bleibt beim Effekt

    # ── Anderer Tab aktiv (selbst selektiert) -> Effekt besitzt den Dimmer ────
    def test_matrix_tab_keeps_effect_even_if_selected(self):
        st = _make_state()
        st.function_manager.writes = {_INT7: 200}
        st.programmer = {7: {"intensity": 0}}
        st.selected_fids = [7]
        st.programmer_focus = "Matrix"
        st._render_frame(0.02)
        self.assertEqual(self._v(st, _INT7), 200)

    # ── Gegenprobe: ohne Effekt bleibt die Programmer-Intensitaet absolut ─────
    def test_no_effect_programmer_absolute(self):
        st = _make_state()
        st.programmer = {7: {"intensity": 0}}        # explizit gedimmt, kein Effekt
        st.selected_fids = [7]
        st.programmer_focus = "Intensity"
        st._render_frame(0.02)
        self.assertEqual(self._v(st, _INT7), 0)

    # ── Echte Master wirken weiter: Submaster skaliert den Effekt-Dimmer ──────
    def test_submaster_still_scales_owned_dimmer(self):
        st = _make_state()
        st.function_manager.writes = {_INT7: 200}
        st.programmer = {7: {"intensity": 0}}        # Programmer wirkt NICHT (Effekt besitzt)
        st.submaster_level = 0.5
        st._render_frame(0.02)
        self.assertAlmostEqual(self._v(st, _INT7), 100, delta=2)


if __name__ == "__main__":
    unittest.main()
