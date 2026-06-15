"""Regressionstests fuer Phase 0 (Live-Sicherheit / Isolation):

- ISO-03: Simple Desk ist eine deterministische Renderer-Schicht statt Roh-Bypass.
  -> kein Flackern auf gepatchten Kanaelen (jeder Frame gleicher Wert),
  -> kein 'Zombie' auf freien Kanaelen (Clear gibt sie im naechsten Frame frei).
- ISO-01: programmer_active()/simple_desk_active() zaehlen aktive Fremdwerte.
- ISO-02: clear_simple_desk()/clear_all_non_vc() leeren nur aktive Werte.

Ergaenzt tests/test_render_frame.py (Merge-Vertrag Default->Funktion->Executor->
Programmer->SimpleDesk).
"""
import os
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
    """Fake-FunctionManager: schreibt optional einen Kanal (Effekt-Simulation)."""
    def __init__(self):
        self.addr = None
        self.val = 0

    def tick(self, universes, patch_cache, dt):
        if self.addr is not None and 1 in universes:
            universes[1].set_channel(self.addr, self.val)


def _make_state():
    st = AppState.__new__(AppState)            # ohne __init__ (keine DB/Threads)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.simple_desk = {}
    st.simple_desk_override = True              # Override-Pfade testen (Default ist False)
    st.playback_engine = None
    st.function_manager = _FM()
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st._patch_cache = [_Fx(1, 1, 10)]          # Adressen 10..13
    import threading as _t, types as _ty
    st._prog_lock = _t.RLock()
    st._sd_lock = _t.RLock()
    st._callbacks = []
    st._ui_marshaller = None
    st._ui_thread_id = None
    st.sync = get_sync()
    st.output_manager = _ty.SimpleNamespace(set_gm_address_mask=lambda m: None)
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


class SimpleDeskLayerTest(_Base):
    def test_sd_overrides_patched_channel_no_flicker(self):
        # Programmer setzt Intensitaet (Adr 10) auf 200, Simple Desk auf 50.
        self.st.programmer = {1: {"intensity": 200}}
        self.st.set_simple_desk_channel(1, 10, 50)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 50)   # SD gewinnt (oberste Schicht)
        # Zweiter Frame: identischer Wert (kein Flackern, frueher ueberschrieb der
        # Renderer den Roh-Write Frame fuer Frame).
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 50)

    def test_sd_clear_releases_patched_channel(self):
        self.st.programmer = {1: {"intensity": 200}}
        self.st.set_simple_desk_channel(1, 10, 50)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 50)
        self.st.clear_simple_desk(1)              # Override weg
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)  # faellt auf Programmer zurueck

    def test_sd_free_channel_no_zombie(self):
        # Freier (nicht gepatchter) Kanal 300: SD setzt 123 -> committed.
        self.st.set_simple_desk_channel(1, 300, 123)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(300), 123)
        # Clear -> naechster Frame gibt den Kanal frei (0), kein haengender Wert.
        self.st.clear_simple_desk()
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(300), 0)

    def test_sd_set_all(self):
        self.st.set_simple_desk_all(1, 255)
        self.assertEqual(self.st.simple_desk_active(), 512)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 255)   # gepatcht
        self.assertEqual(self.live.get_channel(300), 255)  # frei

    def test_override_off_is_display_only(self):
        # Override AUS = reine Anzeige: gesetzte SD-Werte wirken NICHT auf die
        # Ausgabe und zaehlen NICHT als aktiv.
        self.st.simple_desk_override = False
        self.st.programmer = {1: {"intensity": 200}}
        self.st.set_simple_desk_channel(1, 10, 50)      # waere im Override 50
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)  # Programmer sichtbar, SD ignoriert
        self.assertEqual(self.st.simple_desk_active(), 0)

    def test_set_override_off_releases_and_clears(self):
        self.st.set_simple_desk_channel(1, 300, 123)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(300), 123)
        self.st.set_simple_desk_override(False)          # Override aus -> verwirft Werte
        self.assertEqual(self.st.simple_desk_active(), 0)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(300), 0)  # freigegeben

    def test_sd_value_clamped_and_range_guarded(self):
        self.st.set_simple_desk_channel(1, 10, 999)        # > 255 -> 255
        self.st.set_simple_desk_channel(1, 0, 100)         # Kanal 0 -> ignoriert
        self.st.set_simple_desk_channel(1, 513, 100)       # Kanal 513 -> ignoriert
        self.assertEqual(self.st.simple_desk_active(), 1)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 255)


class ActiveAndClearTest(_Base):
    def test_active_counters(self):
        self.assertEqual(self.st.programmer_active(), 0)
        self.assertEqual(self.st.simple_desk_active(), 0)
        self.st.programmer = {1: {"intensity": 200, "color_r": 10}}
        self.st.set_simple_desk_channel(1, 5, 50)
        self.assertEqual(self.st.programmer_active(), 2)
        self.assertEqual(self.st.simple_desk_active(), 1)

    def test_clear_all_non_vc(self):
        self.st.programmer = {1: {"intensity": 200}}
        self.st.set_simple_desk_channel(1, 5, 50)
        self.st.clear_all_non_vc()
        self.assertEqual(self.st.programmer_active(), 0)
        self.assertEqual(self.st.simple_desk_active(), 0)

    def test_clear_all_non_vc_keeps_running_function(self):
        # Ein laufender Effekt (Funktion) darf von clear_all_non_vc NICHT
        # gestoppt werden — Clear betrifft nur manuelle Fremdwerte.
        self.st.function_manager.addr = 12      # Funktion treibt Adresse 12 (color_g)
        self.st.function_manager.val = 180
        self.st.programmer = {1: {"intensity": 200}}
        self.st.set_simple_desk_channel(1, 10, 40)
        self.st._render_frame(0.02)
        self.st.clear_all_non_vc()
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(12), 180)   # Funktion laeuft weiter
        # Programmer- und Simple-Desk-Override sind weg (Zaehler 0)…
        self.assertEqual(self.st.programmer_active(), 0)
        self.assertEqual(self.st.simple_desk_active(), 0)
        # …der laufende Farb-Effekt (color_g=180) lichtet das Fixture jetzt aber
        # implizit (4a²: „Farbe heisst sichtbar") — der Dimmer geht auf voll,
        # statt wie frueher dunkel zu bleiben. Der explizite Programmer-Wert (200)
        # bzw. SD-Wert (40) ist verschwunden; die 255 kommt aus der Grundhelligkeit.
        self.assertEqual(self.live.get_channel(10), 255)


if __name__ == "__main__":
    unittest.main()
