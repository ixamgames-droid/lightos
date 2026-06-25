"""Zuweisbarer Submaster (UI-13 / ENG-09).

Der VC-Submaster-Fader wirkt nicht mehr nur global auf alles, sondern laesst sich
auf bestimmte Geraete/Gruppen zuweisen (Reichweite Alle/Gruppe/Auswahl). Auf den
zugewiesenen Geraeten dimmt er rein multiplikativ und kombiniert sich mit dem
Grand-Master (Hauptmaster 50 % x Submaster 50 % = 25 % — aber nur dort).

Drei Ebenen:
  1. OutputManager-API: globaler vs. zugewiesener Submaster, Produkt, Aufraeumen.
  2. Renderer (_render_frame Schritt 4b): zugewiesener Submaster dimmt nur seine
     fids, andere Fixtures bleiben unberuehrt; global = unveraendert (Regression).
  3. VCSlider._apply: Reichweite -> set_submaster(id, level, fids).
"""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.dmx.output_manager import OutputManager


# ── 1. OutputManager-API ─────────────────────────────────────────────────────

class TestOutputManagerSubmasterAPI(unittest.TestCase):
    def setUp(self):
        self.om = OutputManager()

    def test_global_submaster_in_effective(self):
        self.om.set_submaster("a", 0.5)            # fids=None -> global
        self.assertAlmostEqual(self.om.effective_submaster(), 0.5)
        # Global wirkt NICHT als gezielter Faktor:
        self.assertEqual(self.om.submaster_factor_for(1), 1.0)

    def test_assigned_submaster_only_targets(self):
        self.om.set_submaster("a", 0.5, [1])
        # Zugewiesen -> zaehlt NICHT zum globalen Faktor:
        self.assertEqual(self.om.effective_submaster(), 1.0)
        self.assertAlmostEqual(self.om.submaster_factor_for(1), 0.5)
        self.assertEqual(self.om.submaster_factor_for(2), 1.0)

    def test_multiple_assigned_multiply_per_fixture(self):
        self.om.set_submaster("a", 0.5, [1])
        self.om.set_submaster("b", 0.5, [1, 2])
        self.assertAlmostEqual(self.om.submaster_factor_for(1), 0.25)   # beide treffen
        self.assertAlmostEqual(self.om.submaster_factor_for(2), 0.5)    # nur b

    def test_clear_submaster(self):
        self.om.set_submaster("a", 0.5, [1])
        self.om.clear_submaster("a")
        self.assertEqual(self.om.submaster_factor_for(1), 1.0)

    def test_distinct_slots_do_not_overwrite(self):
        # Zwei globale Submaster (eigene Slots) multiplizieren sich, statt sich
        # gegenseitig zu ueberschreiben (frueher teilten sie Slot 0).
        self.om.set_submaster("a", 0.5)
        self.om.set_submaster("b", 0.5)
        self.assertAlmostEqual(self.om.effective_submaster(), 0.25)

    def test_backward_compatible_two_arg_call(self):
        self.om.set_submaster(0, 0.4)              # alte 2-Argument-Signatur
        self.assertAlmostEqual(self.om.effective_submaster(), 0.4)

    def test_level_clamped(self):
        self.om.set_submaster("a", 2.0)
        self.assertEqual(self.om.effective_submaster(), 1.0)
        self.om.set_submaster("b", -1.0, [1])
        self.assertEqual(self.om.submaster_factor_for(1), 0.0)


# ── 2. Renderer-Integration (zwei Fixtures) ──────────────────────────────────

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


class _FM2:
    """Fake-FunctionManager: treibt zwei Dimmer (Addr 1 = fid1, Addr 5 = fid2)
    auf voll (255)."""
    def tick(self, universes, patch_cache, dt):
        if 1 in universes:
            universes[1].set_channel(1, 255)
            universes[1].set_channel(5, 255)


def _make_state_2fx():
    """AppState mit zwei Dimmer-Fixtures (fid1@Addr1, fid2@Addr5) und echtem
    OutputManager (fuer set_submaster/effective_submaster/submaster_factor_for)."""
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM2()
    fx1 = _Fx(1, 1, 1)
    fx2 = _Fx(2, 1, 5)
    st._fix_index = {1: (fx1, [_Ch("intensity", 1, 0)]),
                     2: (fx2, [_Ch("intensity", 1, 0)])}
    st._default_frame = {1: bytes(512)}
    st._commit_spans = {1: [(1, 5)]}              # (start, length) -> Addr 1..5
    st._patched_set = {1: frozenset({1, 5})}
    st._engine_extra_prev = {}
    st._patch_cache = [fx1, fx2]
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    import threading as _t
    st._prog_lock = _t.RLock()
    st.output_manager = OutputManager()
    return st


class TestRendererScopedSubmaster(unittest.TestCase):
    def _v(self, st, addr):
        return st.universes[1].get_channel(addr)

    def test_no_submaster_both_full(self):
        st = _make_state_2fx()
        st._render_frame(0.02)
        self.assertEqual(self._v(st, 1), 255)
        self.assertEqual(self._v(st, 5), 255)

    def test_global_submaster_scales_both(self):
        st = _make_state_2fx()
        st.output_manager.set_submaster("g", 0.5)          # global
        st._render_frame(0.02)
        self.assertAlmostEqual(self._v(st, 1), 127, delta=1)
        self.assertAlmostEqual(self._v(st, 5), 127, delta=1)

    def test_assigned_submaster_scopes_to_fid(self):
        st = _make_state_2fx()
        st.output_manager.set_submaster("s", 0.5, [1])     # nur fid1
        st._render_frame(0.02)
        self.assertAlmostEqual(self._v(st, 1), 127, delta=1)   # gedimmt
        self.assertEqual(self._v(st, 5), 255)                  # unberuehrt

    def test_assigned_and_global_combine_on_target(self):
        st = _make_state_2fx()
        st.output_manager.set_submaster("g", 0.5)          # global -> beide
        st.output_manager.set_submaster("s", 0.5, [1])     # zusaetzlich nur fid1
        st._render_frame(0.02)
        self.assertAlmostEqual(self._v(st, 1), 64, delta=1)    # 255*0.5*0.5
        self.assertAlmostEqual(self._v(st, 5), 127, delta=1)   # nur global

    def test_assigned_submaster_with_grandmaster_is_25_percent(self):
        # Davids Szenario: Hauptmaster 50 % x (zugewiesener) Submaster 50 % = 25 %
        # auf dem zugewiesenen Geraet; das andere folgt nur dem Grand-Master.
        st = _make_state_2fx()
        st.output_manager.set_submaster("s", 0.5, [1])
        st._render_frame(0.02)
        # Grand-Master-Sende-Stufe nachstellen (output_manager._send_all, maskiert).
        gm, mask = 0.5, {1, 5}
        out = {a: self._v(st, a) for a in (1, 5)}
        for a in mask:
            out[a] = min(255, int(out[a] * gm + 0.5))
        self.assertAlmostEqual(out[1], 64, delta=1)    # 255*0.5*0.5 ~ 25 %
        self.assertAlmostEqual(out[5], 128, delta=1)   # 255*0.5 ~ 50 %


# ── 3. VCSlider._apply Routing (Qt) ──────────────────────────────────────────

from PySide6.QtWidgets import QApplication                      # noqa: E402
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode  # noqa: E402
from src.core.app_state import get_state                        # noqa: E402

_app = QApplication.instance() or QApplication([])


class TestVCSliderSubmasterApply(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.state.output_manager._submasters.clear()

    def tearDown(self):
        self.state.output_manager._submasters.clear()

    def test_scope_all_is_global(self):
        s = VCSlider("Sub")
        s.mode = SliderMode.SUBMASTER
        s.programmer_scope = "all"
        s.value = 128                                  # -> _apply
        self.assertAlmostEqual(self.state.output_manager.effective_submaster(),
                               128 / 255.0, places=3)
        self.assertEqual(self.state.output_manager.submaster_factor_for(1), 1.0)

    def test_scope_group_targets_only_group(self):
        s = VCSlider("Sub")
        s.mode = SliderMode.SUBMASTER
        s.programmer_scope = "group"
        s.programmer_group = "PARs"
        with patch.object(VCSlider, "_group_fids", return_value=[1]):
            s.value = 128
        om = self.state.output_manager
        self.assertEqual(om.effective_submaster(), 1.0)            # nicht global
        self.assertAlmostEqual(om.submaster_factor_for(1), 128 / 255.0, places=3)
        self.assertEqual(om.submaster_factor_for(2), 1.0)

    def test_two_sliders_own_distinct_slots(self):
        s1 = VCSlider("A"); s1.mode = SliderMode.SUBMASTER; s1.programmer_scope = "all"
        s2 = VCSlider("B"); s2.mode = SliderMode.SUBMASTER; s2.programmer_scope = "all"
        s1.value = 128
        s2.value = 128
        # Beide eigene Slots -> multiplizieren (frueher Slot 0 -> Ueberschreiben).
        self.assertAlmostEqual(self.state.output_manager.effective_submaster(),
                               (128 / 255.0) ** 2, places=3)

    def test_serialization_roundtrip(self):
        s = VCSlider("X")
        s.mode = SliderMode.SUBMASTER
        s.programmer_scope = "group"
        s.programmer_group = "Moving Heads"
        s2 = VCSlider("Y")
        s2.apply_dict(s.to_dict())
        self.assertEqual(s2.mode, SliderMode.SUBMASTER)
        self.assertEqual(s2.programmer_scope, "group")
        self.assertEqual(s2.programmer_group, "Moving Heads")


if __name__ == "__main__":
    unittest.main()
