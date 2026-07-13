"""WEB-01: Web-/OSC-Einzelkanal ueber die Input-Override-Schicht.

Frueher schrieben der Web-Handler (``/api/channel``) und der OSC-Handler
(``/lightos/ch``) den Wert DIREKT ins Live-Universe (``universe.set_channel``).
Der zentrale 44-Hz-Renderer (``_render_frame``) ueberschrieb ihn auf GEPATCHTEN
Kanaelen aber jeden Frame wieder — der Wert flackerte und hielt nur ~1 Frame.

Fix: ``AppState.set_input_channel`` legt den Wert in die bereits existierende
Input-Override-Schicht (``input_layer``) und markiert ihn in
``_remote_input_channels``. Der Renderer

  * mischt ihn als REPLACE ein (auch wenn die Universe-Merge-Mode HTP ist), und
  * nimmt ihn — anders als einen Art-Net/sACN-Stream — vom NET-05-Stale-Timeout
    aus (ein Web-POST ist ein diskreter Einzelbefehl, kein Stream).

``clear_remote_input``/``clear_programmer`` geben ihn wieder frei (Release).

Scaffold gespiegelt von tests/test_input_layer.py (Fake-State ohne DB/Threads).
"""
import os
import threading
import time
import types
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
    def tick(self, universes, patch_cache, dt):
        pass


def _make_state():
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.simple_desk = {}
    st.simple_desk_override = False
    st.input_layer = {}
    st.input_merge_modes = {}
    st.input_last_seen = {}
    st._remote_input_channels = {}
    st._input_lock = threading.RLock()
    st.playback_engine = None
    st.function_manager = _FM()
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st._patch_cache = [_Fx(1, 1, 10)]          # Adressen 10..13 gepatcht
    st._prog_lock = threading.RLock()
    st._sd_lock = threading.RLock()
    st._callbacks = []
    st._ui_marshaller = None
    st._ui_thread_id = None
    st.sync = get_sync()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
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


class SetInputChannelTest(_Base):
    def test_stores_in_input_layer_and_marks_remote(self):
        self.st.set_input_channel(1, 10, 200, source="web")
        self.assertEqual(self.st.input_layer[1][10], 200)
        self.assertIn(10, self.st._remote_input_channels[1])

    def test_value_and_channel_guards(self):
        self.st.set_input_channel(1, 10, 999)     # value ueber 255 -> clamp
        self.assertEqual(self.st.input_layer[1][10], 255)
        self.st.set_input_channel(1, 513, 100)    # channel out of range -> No-op
        self.assertNotIn(513, self.st.input_layer.get(1, {}))
        self.st.set_input_channel(9, 10, 100)     # unbekannte Universe -> No-op
        self.assertNotIn(9, self.st.input_layer)

    def test_bad_payload_no_crash(self):
        # kaputte Werte duerfen nicht crashen (never-crash-Stil)
        self.st.set_input_channel(1, 10, "xyz")
        self.st.set_input_channel(1, "x", 10)
        self.assertEqual(self.st.input_layer.get(1, {}).get(10), None)


class RenderHoldTest(_Base):
    def test_value_holds_on_patched_channel_after_render(self):
        """Kern-Regression: der per set_input_channel gesetzte Wert steht nach
        einem _render_frame NOCH auf einem GEPATCHTEN Kanal (Adr 10 = intensity),
        statt vom Renderer ueberschrieben zu werden."""
        self.st.set_input_channel(1, 10, 200, source="web")
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)
        # Und ein zweiter Frame haelt den Wert weiter (kein Flackern/Verfall).
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)

    def test_replace_beats_higher_show_value(self):
        """REPLACE-Semantik: der Web-Wert ersetzt auch einen HOEHEREN Show-Wert
        auf demselben Kanal (nicht HTP)."""
        self.st.programmer = {1: {"intensity": 250}}    # Adr 10 = 250
        self.st.set_input_channel(1, 10, 30, source="web")
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 30)

    def test_survives_stale_timeout(self):
        """WEB-01/NET-05: ein Web-POST ist ein diskreter Befehl — er darf NICHT
        vom Source-Timeout verworfen werden. Selbst nach kuenstlichem Altern
        (kein last_seen-Eintrag -> nie stale) haelt der Wert."""
        self.st.set_input_channel(1, 10, 200, source="web")
        self.st._render_frame(0.02)
        # Ein Art-Net-Stale-Szenario simulieren: last_seen weit in der Vergangenheit.
        self.st.input_last_seen[1] = time.monotonic() - (A.INPUT_SOURCE_TIMEOUT_S + 5.0)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)   # haelt trotzdem
        self.assertIn(10, self.st.input_layer.get(1, {}))

    def test_remote_survives_but_artnet_on_same_universe_expires(self):
        """Gemischte Universe: Art-Net-Kanal (Adr 11) laeuft ueber den Stream und
        soll bei Stale verfallen, der Web-Kanal (Adr 10) bleibt."""
        self.st.apply_input_merge(1, bytes([0] * 10 + [180]), "HTP")  # Adr 11 = 180
        self.st.set_input_channel(1, 10, 200, source="web")
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)
        self.assertEqual(self.live.get_channel(11), 180)
        # Stream veraltet -> Adr 11 faellt, Adr 10 (Web) bleibt.
        self.st.input_last_seen[1] = time.monotonic() - (A.INPUT_SOURCE_TIMEOUT_S + 5.0)
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(11), 0)
        self.assertEqual(self.live.get_channel(10), 200)


class ClearTest(_Base):
    def test_clear_remote_input_releases_value(self):
        self.st.set_input_channel(1, 10, 200, source="web")
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)
        self.st.clear_remote_input()
        self.assertEqual(self.st._remote_input_channels, {})
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 0)     # freigegeben

    def test_clear_programmer_also_clears_remote_input(self):
        """clear_programmer(None) ist der Release-Pfad und raeumt die Web/OSC-
        Overrides mit."""
        self.st.set_input_channel(1, 10, 200, source="web")
        self.st.clear_programmer()
        self.assertEqual(self.st._remote_input_channels, {})
        self.assertNotIn(10, self.st.input_layer.get(1, {}))

    def test_clear_keeps_artnet_on_same_universe(self):
        self.st.apply_input_merge(1, bytes([0] * 10 + [180]), "HTP")  # Adr 11
        self.st.set_input_channel(1, 10, 200, source="web")
        self.st.clear_remote_input()
        self.assertNotIn(10, self.st.input_layer.get(1, {}))
        self.assertEqual(self.st.input_layer[1][11], 180)   # Art-Net bleibt


if __name__ == "__main__":
    unittest.main()
