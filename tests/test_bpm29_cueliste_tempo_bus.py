"""BPM-29: Taktgebundene Cuelisten waehlbar an einen Tempo-Bus (A–D) koppeln.

Vorher hing ``beat_sync`` nur am globalen BPMManager: eine Cueliste konnte
nicht im Takt von Bus A schalten, waehrend die globale BPM anders lief.
Jetzt: ``CueStack.tempo_bus`` ("" = global, bisheriges Verhalten); ein
gekoppelter Bus treibt die Liste ueber ``treibe_bus_cuelisten`` (Render-Thread
nach ``advance_frame``), der BPMManager laesst solche Listen aus. Speichern/Laden
in der Show; Alt-Shows ohne Feld bleiben global.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.cue import Cue
from src.core.engine.cue_stack import CueStack, treibe_bus_cuelisten
from src.core.engine.tempo_bus import TempoBusManager


def _stack(bus="", per=1, n=4):
    s = CueStack("t")
    s.mode = "loop"
    s.beat_sync = True
    s.beats_per_cue = per
    s.tempo_bus = bus
    for i in range(n):
        s.add_cue(Cue(number=i + 1, values={1: {"intensity": 255}}))
    return s


class _Bus:
    def __init__(self):
        self.pos = 0.0

    def position(self):
        return self.pos


class _Mgr:
    def __init__(self):
        self.busse = {"A": _Bus(), "B": _Bus()}
        self.gefragt = []

    def bus_for_effect(self, bid):
        self.gefragt.append(bid)
        return self.busse.get(bid)


class BusTreibtCuelisteTest(unittest.TestCase):
    def test_bus_a_schaltet_pro_ganzem_beat(self):
        s = _stack(bus="A", per=2)
        m = _Mgr()
        s.go()
        treibe_bus_cuelisten([s], m)          # Anker bei Beat 0
        self.assertEqual(s.current_index, 0)
        m.busse["A"].pos = 0.9
        treibe_bus_cuelisten([s], m)
        self.assertEqual(s.current_index, 0)
        m.busse["A"].pos = 1.05               # 1. Beat — per=2, haelt
        treibe_bus_cuelisten([s], m)
        self.assertEqual(s.current_index, 0)
        m.busse["A"].pos = 2.01               # 2. Beat — weiter
        treibe_bus_cuelisten([s], m)
        self.assertEqual(s.current_index, 1)
        s.stop()

    def test_bus_b_unabhaengig_von_bus_a(self):
        a, b = _stack(bus="A"), _stack(bus="B")
        m = _Mgr()
        a.go(); b.go()
        treibe_bus_cuelisten([a, b], m)
        m.busse["A"].pos = 3.0                # nur Bus A laeuft
        for p in (1.0, 2.0, 3.0):
            m.busse["A"].pos = p
            treibe_bus_cuelisten([a, b], m)
        self.assertEqual(a.current_index, 3)
        self.assertEqual(b.current_index, 0)
        a.stop(); b.stop()

    def test_globale_liste_wird_vom_bus_nicht_getrieben(self):
        s = _stack(bus="")
        m = _Mgr()
        s.go()
        treibe_bus_cuelisten([s], m)
        m.busse["A"].pos = 5.0
        treibe_bus_cuelisten([s], m)
        self.assertEqual(s.current_index, 0)
        self.assertEqual(m.gefragt, [])
        s.stop()

    def test_rueck_und_grosser_sprung_setzen_nur_anker(self):
        s = _stack(bus="A")
        m = _Mgr()
        s.go()
        treibe_bus_cuelisten([s], m)
        m.busse["A"].pos = 100.0              # Sprung > MAX → kein Cue-Sturm
        treibe_bus_cuelisten([s], m)
        self.assertEqual(s.current_index, 0)
        m.busse["A"].pos = 0.0                # Reset rueckwaerts
        treibe_bus_cuelisten([s], m)
        self.assertEqual(s.current_index, 0)
        m.busse["A"].pos = 1.0
        treibe_bus_cuelisten([s], m)
        self.assertEqual(s.current_index, 1)
        s.stop()

    def test_vor_dem_start_gezaehlte_beats_werden_nicht_nachgeholt(self):
        s = _stack(bus="A")
        m = _Mgr()
        for p in (0.0, 1.0, 2.0, 3.0):        # Liste steht noch
            m.busse["A"].pos = p
            treibe_bus_cuelisten([s], m)
        s.go()
        self.assertEqual(s.current_index, 0)
        m.busse["A"].pos = 4.0
        treibe_bus_cuelisten([s], m)
        self.assertEqual(s.current_index, 1)
        s.stop()

    def test_buswechsel_zaehlt_keine_fremde_positionsdifferenz(self):
        # A steht bei 2, B bei 5: Umkoppeln A -> B darf nicht 3 Beats ausloesen.
        s = _stack(bus="A", per=1)
        m = _Mgr()
        s.go()
        m.busse["A"].pos = 2.0
        m.busse["B"].pos = 5.0
        treibe_bus_cuelisten([s], m)          # Anker auf A=2
        s.tempo_bus = "B"
        treibe_bus_cuelisten([s], m)          # erst neu ankern auf B=5
        self.assertEqual(s.current_index, 0)
        m.busse["B"].pos = 6.0
        treibe_bus_cuelisten([s], m)
        self.assertEqual(s.current_index, 1)

    def test_zurueckkoppeln_nach_global_zaehlt_nicht_gegen_alten_anker(self):
        s = _stack(bus="A", per=1)
        m = _Mgr()
        s.go()
        m.busse["A"].pos = 1.0
        treibe_bus_cuelisten([s], m)          # Anker A=1
        s.tempo_bus = ""
        m.busse["A"].pos = 3.0
        treibe_bus_cuelisten([s], m)          # global: Bus treibt nicht
        s.tempo_bus = "A"
        treibe_bus_cuelisten([s], m)          # neu ankern, kein Nachholen
        self.assertEqual(s.current_index, 0)

    def test_echter_bus_manager_bus_a(self):
        """Mit dem echten TempoBusManager: Bus A auf 120 BPM, 0,5 s = 1 Beat."""
        tbm = TempoBusManager()
        tbm.ensure_bus("A").set_bpm(120.0)
        s = _stack(bus="A")
        s.go()
        treibe_bus_cuelisten([s], tbm)
        for _ in range(5):
            tbm.get("A").advance_frame(0.11)  # 0,55 s → ein ganzer Beat
        treibe_bus_cuelisten([s], tbm)
        self.assertEqual(s.current_index, 1)
        s.stop()


class BpmManagerLaesstBusListenAusTest(unittest.TestCase):
    def test_globaler_beat_treibt_nur_globale_liste(self):
        from src.core import app_state as A
        from src.core.engine.bpm_manager import BPMManager
        glob, bus = _stack(bus=""), _stack(bus="A")
        glob.go(); bus.go()
        st = mock.Mock()
        st.cue_stacks = [glob, bus]
        with mock.patch.object(A, "vorhandener_state", return_value=st):
            BPMManager()._emit_beat()
        self.assertEqual(glob.current_index, 1)
        self.assertEqual(bus.current_index, 0)   # Bus A treibt, nicht global
        glob.stop(); bus.stop()


class SerialisierungTest(unittest.TestCase):
    def test_roundtrip_bus(self):
        d = _stack(bus="C").to_dict()
        self.assertEqual(d["tempo_bus"], "C")
        self.assertEqual(CueStack.from_dict(d).tempo_bus, "C")

    def test_global_schreibt_kein_feld(self):
        self.assertNotIn("tempo_bus", _stack(bus="").to_dict())

    def test_altshow_bleibt_global(self):
        s = CueStack.from_dict({"name": "x", "beat_sync": True, "cues": []})
        self.assertEqual(s.tempo_bus, "")

    def test_aliase_normalisiert(self):
        for roh in ("global", " Default ", None, 3):
            self.assertEqual(CueStack.from_dict(
                {"name": "x", "tempo_bus": roh, "cues": []}).tempo_bus, "")
        self.assertEqual(CueStack.from_dict(
            {"name": "x", "tempo_bus": " B ", "cues": []}).tempo_bus, "B")


class EditorTaktAuswahlTest(unittest.TestCase):
    """Echte PlaybackView (offscreen, Sandkasten-AppState wie test_ui72)."""

    def test_takt_combo_setzt_und_spiegelt_bus(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.core.app_state import get_state
        from src.ui.views.playback_view import PlaybackView
        state = get_state()
        alt = list(state.cue_stacks)
        state.cue_stacks.clear()
        try:
            liste = state.new_cue_stack("Takt-Liste")
            view = PlaybackView()
            view._combo_stack.setCurrentIndex(0)
            self.assertIs(view._current_stack, liste)
            daten = [view._combo_takt.itemData(i)
                     for i in range(view._combo_takt.count())]
            self.assertEqual(daten, ["", "A", "B", "C", "D"])
            self.assertEqual(view._combo_takt.currentText(), "global")
            view._combo_takt.setCurrentIndex(view._combo_takt.findData("B"))
            self.assertEqual(liste.tempo_bus, "B")
            zweite = state.new_cue_stack("Zweite")
            zweite.tempo_bus = "D"
            view._refresh_stack_combo()
            view._combo_stack.setCurrentIndex(1)
            self.assertEqual(view._combo_takt.currentData(), "D")
            view._combo_stack.setCurrentIndex(0)
            self.assertEqual(view._combo_takt.currentData(), "B")
            view.deleteLater()
        finally:
            state.cue_stacks.clear()
            state.cue_stacks.extend(alt)
            state.gewaehlte_cueliste = None

class RenderFrameTreibtBusListeTest(unittest.TestCase):
    """Der Aufruf in ``AppState._render_frame`` (nach ``advance_frame``)."""

    def _state(self):
        import threading
        import types
        from src.core.app_state import AppState
        from src.core.dmx.universe import Universe
        st = AppState.__new__(AppState)
        st.universes = {1: Universe(1)}
        st.programmer = {}
        st.playback_engine = None
        st.function_manager = types.SimpleNamespace(
            tick=lambda universes, patch, dt: None)
        st._fix_index = {}
        st._default_frame = {1: bytes(512)}
        st._commit_spans = {1: []}
        st._patched_set = {1: frozenset()}
        st._engine_extra_prev = {}
        st._patch_cache = []
        st.submaster_level = 1.0
        st.fixture_dimmers = {}
        st._prog_lock = threading.RLock()
        st.output_manager = types.SimpleNamespace(
            set_gm_address_mask=lambda m: None)
        return st

    def test_render_frame_schaltet_bus_liste(self):
        mgr = TempoBusManager()
        bus = mgr.ensure_bus("A")
        bus.set_bpm(120.0)
        st = self._state()
        s = _stack(bus="A", per=1)
        s.go()
        st.cue_stacks = [s]
        with mock.patch("src.core.engine.tempo_bus.get_tempo_bus_manager",
                        return_value=mgr):
            st._render_frame(0.05)                # ankern
            self.assertEqual(s.current_index, 0)
            for _ in range(11):                   # 0,55 s bei 120 BPM > 1 Beat
                st._render_frame(0.05)
        self.assertEqual(s.current_index, 1)


if __name__ == "__main__":
    unittest.main()
