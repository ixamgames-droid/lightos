"""LAS-24: der Grand Master erreichte Laser ohne Dimmer nicht.

``_build_gm_mask`` nimmt nur Dimmer- und additive Farbkanaele. Ein Laser wie der
SH-LASER3W (Betriebsart-Kanal ``shutter``: 0-41 „Laser off“, 42-83 „Manual“)
hat keinen davon — bei GM 0 lief er weiter.

Jetzt: Laser ohne Dimmer/Farbe bekommen eine eigene Aus-Maske
(``{adresse: aus_wert}`` aus den Profil-Bereichen). Bei GM unter
``OutputManager.GM_LASER_AUS_SCHWELLE`` setzt der Sende-Pfad diese Adressen NACH
Channel-Modifier und GM-Skalierung auf den Aus-Wert. Dazwischen bleibt der
Laser unveraendert — eine Betriebsart laesst sich nicht stufenlos dimmen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState
from src.core.dmx.output_manager import OutputManager
from src.core.engine.channel_modifier import (
    ChannelModifier, CurveType, get_modifier_manager,
)


class _Rg:
    def __init__(self, von, bis, name, kind=""):
        self.range_from, self.range_to, self.name, self.kind = von, bis, name, kind


class _Ch:
    def __init__(self, attr, num, ranges=()):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.ranges = list(ranges)


class _Fx:
    protocol = ""

    def __init__(self, fid, universe, address, ftype=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = ftype


# SH-LASER3W (Auszug): Betriebsart mit „closed“-Bereich, Muster, Position.
_LASER3W = [
    _Ch("shutter", 1, [_Rg(0, 41, "Laser off", "closed"),
                       _Rg(42, 83, "Manual Control", "open"),
                       _Rg(84, 125, "Auto run animation effect")]),
    _Ch("laser_bank", 2), _Ch("laser_x", 3), _Ch("laser_y", 4)]
# ZQB370: Betriebsart als macro, Aus-Bereich nur per NAME belegt.
_ZQB370 = [_Ch("macro", 1, [_Rg(0, 49, "Laser Off"), _Rg(50, 99, "Static Pattern")]),
           _Ch("laser_bank", 2)]
# Laser mit Dimmer: den regelt der GM schon regulaer.
_LASER_DIM = [_Ch("intensity", 1), _Ch("shutter", 2), _Ch("laser_x", 3)]
# Macro ohne Aus-Bereich: 0 waere womoeglich ein Auto-Programm -> nicht anfassen.
_LASER_MACRO_OHNE_AUS = [_Ch("macro", 1, [_Rg(0, 99, "Auto")]), _Ch("laser_x", 2)]


def _st():
    return AppState.__new__(AppState)


class BuildMaskTest(unittest.TestCase):
    def test_laser3w_shutter_off_value_from_closed_range(self):
        m = _st()._build_gm_laser_aus_mask({7: (_Fx(7, 1, 10, "laser"), _LASER3W)})
        self.assertEqual(m, {1: {10: 0}})

    def test_closed_range_lower_bound_used(self):
        chans = [_Ch("shutter", 1, [_Rg(0, 9, "Strobe"), _Rg(10, 20, "Aus", "closed")]),
                 _Ch("laser_x", 2)]
        m = _st()._build_gm_laser_aus_mask({1: (_Fx(1, 2, 100), chans)})
        self.assertEqual(m, {2: {100: 10}})

    def test_off_by_range_name_on_macro(self):
        m = _st()._build_gm_laser_aus_mask({3: (_Fx(3, 1, 20, "laser"), _ZQB370)})
        self.assertEqual(m, {1: {20: 0}})

    def test_laser_with_dimmer_and_non_laser_excluded(self):
        st = _st()
        self.assertEqual(st._build_gm_laser_aus_mask(
            {1: (_Fx(1, 1, 1, "laser"), _LASER_DIM)}), {})
        # Ein Strobe/PAR ohne Laser-Merkmal bleibt aussen vor.
        self.assertEqual(st._build_gm_laser_aus_mask(
            {2: (_Fx(2, 1, 50), [_Ch("shutter", 1)])}), {})

    def test_macro_without_off_range_untouched(self):
        self.assertEqual(_st()._build_gm_laser_aus_mask(
            {1: (_Fx(1, 1, 1, "laser"), _LASER_MACRO_OHNE_AUS)}), {})

    def test_shutter_without_ranges_falls_back_to_zero(self):
        chans = [_Ch("shutter", 1), _Ch("laser_x", 2)]
        self.assertEqual(_st()._build_gm_laser_aus_mask(
            {1: (_Fx(1, 1, 30, "laser"), chans)}), {1: {30: 0}})


class SendPathTest(unittest.TestCase):
    """Echter OutputManager: was im Display-Frame (= gesendet) landet."""

    def setUp(self):
        self.om = OutputManager()
        self.u = self.om.add_universe(1)
        self.mgr = get_modifier_manager()
        self.mgr.clear()
        # SH-LASER3W auf 10 (shutter=60 = Manual/an), PAR-Dimmer auf 20.
        self.u.set_channel(10, 60)
        self.u.set_channel(11, 77)
        self.u.set_channel(20, 200)
        self.om.set_gm_address_mask({1: frozenset({20})})
        self.om.set_gm_laser_aus_mask({1: {10: 0}})

    def tearDown(self):
        self.mgr.clear()

    def _out(self, addr):
        return self.om._display_frame[1][addr - 1]

    def test_gm_zero_switches_laser_off(self):
        self.om.grand_master = 0.0
        self.om._send_all()
        self.assertEqual(self._out(10), 0)        # Betriebsart „Laser off“
        self.assertEqual(self._out(11), 77)       # Muster unberuehrt
        self.assertEqual(self._out(20), 0)        # PAR regulaer gedimmt

    def test_gm_half_leaves_laser_unchanged_documented(self):
        # Dokumentiert: kein stufenloses Dimmen eines Lasers ueber die Betriebsart.
        self.om.grand_master = 0.5
        self.om._send_all()
        self.assertEqual(self._out(10), 60)
        self.assertEqual(self._out(20), 100)

    def test_gm_full_leaves_laser_unchanged(self):
        self.om.grand_master = 1.0
        self.om._send_all()
        self.assertEqual(self._out(10), 60)

    def test_inverse_modifier_cannot_reopen_laser_at_gm_zero(self):
        # Renderer hat 0 (=aus) im Puffer, INVERSE macht 255 (=Manual an) daraus.
        self.u.set_channel(10, 0)
        self.mgr.add(ChannelModifier(universe=1, address=10, curve=CurveType.INVERSE))
        self.om.grand_master = 0.0
        self.om._send_all()
        self.assertEqual(self._out(10), 0)

    def test_load_window_keeps_laser_off_with_empty_live_mask(self):
        # Lade-Sperre: Masken vom Start eingefroren; der reset-first leert die
        # Live-Maske — der Laser muss bei GM 0 trotzdem aus bleiben.
        self.om.grand_master = 0.0
        with self.om.lade_sperre():
            self.om.set_gm_laser_aus_mask({})
            self.om._send_all()
            self.assertEqual(self._out(10), 0)

    def test_estop_still_wins(self):
        self.om.grand_master = 0.5
        self.om.set_laser_estop_mask({1: frozenset({10, 11})})
        self.om._send_all()
        self.assertEqual(self._out(10), 0)
        self.assertEqual(self._out(11), 0)


class AppStatePushTest(unittest.TestCase):
    """Der Plan-Rebuild schiebt die Maske an den OutputManager."""

    def test_rebuild_pushes_mask(self):
        import threading
        import types
        import src.core.app_state as A
        from src.core.dmx.universe import Universe
        orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _LASER3W
        try:
            st = AppState.__new__(AppState)
            st.universes = {1: Universe(1)}
            st.programmer = {}
            st.playback_engine = None
            st.function_manager = types.SimpleNamespace(tick=lambda *a, **k: None)
            st._patch_cache = [_Fx(7, 1, 10, "laser")]
            st._prog_lock = threading.RLock()
            st.output_manager = OutputManager()
            st.laser_estop_active = False
            st._laser_estop_addrs = {}
            st._laser_fids = frozenset()
            st.base_levels = {}
            st._engine_extra_prev = {}
            st._suppress_emits = True
            st._rebuild_render_plan()
            self.assertEqual(st.output_manager._gm_laser_aus_mask, {1: {10: 0}})
        finally:
            A.get_channels_for_patched = orig


# ── Review-Befunde M1/M2/N1 ─────────────────────────────────────────────────

def _chn(attr, num, name, ranges=()):
    ch = _Ch(attr, num, ranges)
    ch.name = name
    return ch


# DJ Lase BlueStar MK-II LED (Auszug): Dimmer (Kanal 6) nur fuer die LED,
# Laser rot/gruen per „Laser off“ an Macro-Kanaelen.
_BLUESTAR = [
    _chn("macro", 1, "Operating mode selection",
         [_Rg(0, 51, "Laser off"), _Rg(52, 102, "Automatic show")]),
    _chn("macro", 2, "Red laser",
         [_Rg(0, 4, "Laser off"), _Rg(5, 127, "Laser is constantly on")]),
    _chn("macro", 3, "Green laser",
         [_Rg(0, 4, "Laser off"), _Rg(5, 127, "Laser is constantly on")]),
    _chn("intensity", 6, "Dimmer of the blue LED background illumination"),
    _chn("shutter", 7, "Strobe effect of the blue LED",
         [_Rg(0, 4, "Background illumination off"), _Rg(5, 127, "on")]),
]


class ReviewMaskTest(unittest.TestCase):
    def test_m2_laser_with_led_dimmer_gets_explicit_laser_off(self):
        """M2: der Dimmer gilt nur fuer die LED -> GM 0 muss die Laser per
        „Laser off“ ausschalten; das bloße „off“ am LED-Shutter zaehlt bei
        Lasern mit Dimmer nicht."""
        m = _st()._build_gm_laser_aus_mask({1: (_Fx(1, 1, 1, "laser"), _BLUESTAR)})
        self.assertEqual(m, {1: {1: 0, 2: 0, 3: 0}})

    def test_m2_dimmer_laser_closed_kind_alone_not_used(self):
        """„closed“ kann bei Lasern mit Dimmer eine Teil-Abdunklung sein
        (DS-1000RGB „Safety zone intensity“) -> nur Namen zaehlen."""
        chans = [_chn("intensity", 1, "Intensity"),
                 _chn("macro", 2, "Safety zone intensity",
                      [_Rg(0, 0, "No reduction"),
                       _Rg(129, 255, "Decrease brightness up to blackout", "closed")]),
                 _chn("laser_x", 3, "X")]
        self.assertEqual(_st()._build_gm_laser_aus_mask(
            {1: (_Fx(1, 1, 1, "laser"), chans)}), {})

    def test_n1_bare_off_on_macro_is_not_laser_off(self):
        """N1: „Macros: Off“ (Galaxian 3D) und „Off, original pattern“
        (CS-1000RGB Mk II) heissen nicht Laser aus."""
        chans = [_chn("macro", 5, "Macros",
                      [_Rg(0, 7, "Off"), _Rg(8, 23, "Macro 1")]),
                 _chn("macro", 9, "Pattern Buildup (drawing)",
                      [_Rg(0, 0, "Off, original pattern"), _Rg(1, 127, "Auto")]),
                 _chn("macro", 8, "Strobe", [_Rg(0, 9, "Strobe OFF", "strobe")]),
                 _chn("laser_x", 2, "X")]
        self.assertEqual(_st()._build_gm_laser_aus_mask(
            {1: (_Fx(1, 1, 1, "laser"), chans)}), {})

    def test_n1_bare_off_on_mode_channel_and_black_out_still_count(self):
        chans = [_chn("macro", 1, "Mode",
                      [_Rg(0, 9, "Laser Black out"), _Rg(10, 60, "Auto")]),
                 _chn("macro", 2, "Betriebsart",
                      [_Rg(0, 20, "Aus"), _Rg(21, 255, "Auto")]),
                 _chn("shutter", 3, "Laser", [_Rg(0, 5, "Off"), _Rg(6, 255, "On")])]
        self.assertEqual(_st()._build_gm_laser_aus_mask(
            {1: (_Fx(1, 1, 1, "laser"), chans)}), {1: {1: 0, 2: 0, 3: 0}})


class ReviewTextTest(unittest.TestCase):
    """M1: Tooltip und „Erste Schritte“ duerfen nicht pauschal versprechen,
    dass GM 0 jeden Laser ohne Dimmer ausschaltet."""

    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _lesen(self, rel):
        with open(os.path.join(self._ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def _gm_absatz(self, text, start):
        i = text.index(start)
        return text[i:text.index("4. **TAP**", i)]

    def test_tooltip_restricts_and_points_to_estop(self):
        src = self._lesen("src/ui/main_window.py")
        i = src.index("Grand Master (0–100 %)")
        tip = src[i:src.index("self._slider_gm.valueChanged", i)]
        self.assertIn("Aus-Wert", tip)
        self.assertIn("NOT-AUS", tip)

    def test_erste_schritte_de_restricts_and_points_to_estop(self):
        gm = self._gm_absatz(self._lesen(
            "docs/anleitung_erste_schritte/ANLEITUNG.md"), "3. **GM**")
        self.assertIn("Aus-Wert", gm)
        self.assertIn("NOT-AUS", gm)

    def test_erste_schritte_en_restricts_and_points_to_estop(self):
        gm = self._gm_absatz(self._lesen(
            "docs/anleitung_erste_schritte/ANLEITUNG.en.md"), "3. **GM**")
        self.assertIn("off value", gm)
        self.assertIn("emergency stop", gm)


if __name__ == "__main__":
    unittest.main()
