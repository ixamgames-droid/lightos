"""Render-Prioritaet auf funktions-getriebenen Nicht-Intensitaets-Kanaelen
(Bug-Hunt 2026-07-12): der Programmer ist die hoechste LTP-Ebene und muss einen
Cue schlagen — auch auf einem Kanal, den zuvor eine Funktion trieb.

Vorher: func_driven (Schutzmaske "Funktion besitzt diesen Farbkanal vor dem
Programmer") wurde VOR den Executoren erfasst und NICHT aktualisiert. Ueberschrieb
ein Cue so einen Farbkanal, blieb die Adresse im Schutz -> der Programmer wurde
ausgesperrt und der CUE-Wert gewann gegen den hoechstprioren Programmer
(Prioritaets-Inversion: untere Ebene schlaegt obere). Jetzt wird jede vom Cue
geschriebene Adresse aus func_driven genommen; rein funktions-getriebene
(cue-unberuehrte) Kanaele bleiben weiterhin vor dem Programmer geschuetzt.
"""
import os
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState
from src.core.dmx.universe import Universe


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num


class _Fx:
    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


class _ColorFM:
    """Funktion, die color_r (Adr 1) auf 180 treibt."""
    def __init__(self, value=180, active=True):
        self.value = value
        self.active = active

    def tick(self, universes, patch_cache, dt):
        if self.active and 1 in universes:
            universes[1].set_channel(1, self.value)


class _PE:
    """Fake-PlaybackEngine: ein Cue setzt color_r."""
    def __init__(self, merged):
        self._merged = merged

    def compute_merged(self):
        return {fid: dict(a) for fid, a in self._merged.items()}


def _make_state(cue_color=None, func_active=True):
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = _PE({1: {"color_r": cue_color}}) if cue_color is not None else None
    st.function_manager = _ColorFM(active=func_active)
    fx = _Fx(1, 1, 1)
    chans = [_Ch("color_r", 1)]
    st._fix_index = {1: (fx, chans)}
    st._default_frame = {1: bytes(512)}
    st._commit_spans = {1: [(1, 1)]}
    st._patched_set = {1: frozenset({1})}
    st._patch_cache = [fx]
    st._engine_extra_prev = {}
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    st.implicit_brightness = False
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    return st

    # (kein weiterer Code)


class ProgrammerCuePriorityTest(unittest.TestCase):
    def _val(self, st):
        return st.universes[1].get_channel(1)

    def test_programmer_beats_cue_on_function_driven_color(self):
        """Kern-Fix: Funktion 180 -> Cue 50 -> Programmer 250 ==> 250 (Programmer)."""
        st = _make_state(cue_color=50, func_active=True)
        st.programmer = {1: {"color_r": 250}}
        st._render_frame(0.02)
        self.assertEqual(self._val(st), 250)

    def test_function_color_still_protected_from_programmer_without_cue(self):
        """Regression: OHNE Cue behaelt die Funktion ihren Farbkanal gegen den
        Programmer (Schutz bleibt fuer cue-unberuehrte Kanaele)."""
        st = _make_state(cue_color=None, func_active=True)
        st.programmer = {1: {"color_r": 250}}
        st._render_frame(0.02)
        self.assertEqual(self._val(st), 180)

    def test_cue_color_without_function_lets_programmer_win(self):
        """Sanity: kein Funktions-Antrieb -> normaler LTP, Programmer schlaegt Cue."""
        st = _make_state(cue_color=50, func_active=False)
        st.programmer = {1: {"color_r": 250}}
        st._render_frame(0.02)
        self.assertEqual(self._val(st), 250)

    def test_cue_color_survives_without_programmer(self):
        """Sanity: Funktion 180 -> Cue 50, kein Programmer ==> 50 (Cue ueber Funktion)."""
        st = _make_state(cue_color=50, func_active=True)
        st._render_frame(0.02)
        self.assertEqual(self._val(st), 50)


if __name__ == "__main__":
    unittest.main()
