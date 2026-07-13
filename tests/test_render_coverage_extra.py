"""QA-25: Ergaenzende Render-Coverage fuer drei bisher unter-getestete Pfade.

Muster: wie test_render_frame / test_dimmer_master — AppState.__new__ (ohne DB/
Threads), Fake-Fixtures + echtes Universe, get_channels_for_patched gepatcht.
Headless (QT_QPA_PLATFORM=offscreen). Reine Tests, kein Produktiv-Code-Change.

Deckt ab:
  (1) Fail-Safe/Blackout: bei aktivem Blackout sendet output_manager._send_all
      NUR Nullen — unabhaengig vom Live-Universe-Inhalt (der Not-Aus-Pfad).
  (2) Multi-Universe Engine-Extra (STAB-14): ein Roh-Kanal (ScriptFunction.setdmx)
      auf einem NICHT gepatchten Universum wird korrekt committed und beim Stop
      des Skripts wieder freigegeben — ohne das gepatchte Universum zu stoeren.
  (3) EE-02 Color-only: ein reiner Farb-Effekt auf einem Fixture OHNE Dimmer-Kanal
      wird von der Programmer-Intensitaet nur multipliziert (Farb-Fallback-Dimmer),
      es entsteht keine separate Intensitaets-Skalierung.
"""
import os
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.output_manager import OutputManager
from src.core.dmx.universe import Universe


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


class _FakeSender:
    """Merkt sich den zuletzt gesendeten DMX-Frame (wie in den GM-Mask-Tests)."""
    def __init__(self):
        self.last = None

    def send_dmx(self, data):
        self.last = data

    def close(self):
        pass


class _MultiFM:
    """Fake-FunctionManager: schreibt konfigurierte (univ, addr, val)-Rohwerte —
    auch auf NICHT gepatchte Universen (ScriptFunction.setdmx-Verhalten)."""
    def __init__(self):
        self.writes: list[tuple[int, int, int]] = []

    def tick(self, universes, patch_cache, dt):
        for univ, addr, val in self.writes:
            u = universes.get(univ)
            if u is not None:
                u.set_channel(addr, val)


def _make_state(universes, function_manager, patch_cache):
    """AppState-Skelett ohne __init__ (keine DB/Threads), analog test_render_frame."""
    st = AppState.__new__(AppState)
    st.universes = {n: Universe(n) for n in universes}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = function_manager
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st._patch_cache = patch_cache
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    return st


# ── (1) Fail-Safe / Blackout ────────────────────────────────────────────────
class BlackoutSendPathTest(unittest.TestCase):
    """Der Not-Aus-Pfad: aktiver Blackout ueberschreibt den kompletten Frame mit
    Nullen, bevor er die Ausgabe-Geraete erreicht — egal welche Werte im Live-
    Universe stehen (Fail-Safe)."""

    def _om(self):
        om = OutputManager()
        u = om.add_universe(1)
        u.set_channel(1, 255)     # Intensitaet voll
        u.set_channel(5, 200)     # Farbe
        u.set_channel(300, 77)    # roher/hoher Kanal
        fake = _FakeSender()
        om._enttec_outputs[1] = fake
        return om, fake

    def test_blackout_sends_all_zero(self):
        om, fake = self._om()
        om.set_blackout(True)
        om._send_all()
        self.assertEqual(len(fake.last), 512)
        self.assertEqual(set(fake.last), {0})   # ausnahmslos alle Bytes 0

    def test_blackout_off_passes_data(self):
        # Gegenprobe: ohne Blackout kommen die echten Werte an (kein Dauer-Null).
        om, fake = self._om()
        om.set_blackout(False)
        om._send_all()
        self.assertEqual(fake.last[0], 255)
        self.assertEqual(fake.last[4], 200)
        self.assertEqual(fake.last[299], 77)

    def test_blackout_ignores_grand_master(self):
        # Blackout gewinnt vor dem Grand-Master-Zweig -> auch bei GM>0 alles 0.
        om, fake = self._om()
        om.grand_master = 1.0
        om.set_blackout(True)
        om._send_all()
        self.assertEqual(set(fake.last), {0})


# ── (2) Multi-Universe Engine-Extra (STAB-14) ───────────────────────────────
class MultiUniverseEngineExtraTest(unittest.TestCase):
    """Zwei Universen: 1 ist gepatcht, 2 ist reines Roh-Universum. Ein per
    setdmx gesetzter Roh-Kanal auf dem NICHT gepatchten Universum 2 landet korrekt
    im Live-Universe und wird beim Stop des Skripts wieder auf 0 freigegeben —
    ohne das gepatchte Universum 1 zu beruehren (STAB-14)."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: [
            _Ch("intensity", 1, 0), _Ch("color_r", 2, 0),
            _Ch("color_g", 3, 0), _Ch("color_b", 4, 0),
        ]
        self.fm = _MultiFM()
        self.st = _make_state([1, 2], self.fm, [_Fx(1, 1, 10)])  # nur Univ 1 gepatcht
        self.st._rebuild_render_plan()
        self.u1 = self.st.universes[1]
        self.u2 = self.st.universes[2]

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_raw_channel_on_unpatched_universe_committed_and_released(self):
        # Univ 2 ist gar nicht gepatcht -> kein Commit-Span, kein Default-Frame.
        self.assertNotIn(2, self.st._commit_spans)
        self.assertNotIn(2, self.st._patched_set)
        # Skript schreibt einen Roh-Kanal auf das Roh-Universum 2.
        self.fm.writes = [(2, 100, 240)]
        self.st._render_frame(0.02)
        self.assertEqual(self.u2.get_channel(100), 240)          # Roh committed
        self.assertEqual(self.st._engine_extra_prev.get(2), {100})
        self.assertEqual(self.u1.get_channel(10), 0)             # Univ 1 unberuehrt
        # Skript stoppt -> naechster Frame gibt den Roh-Kanal wieder frei (0).
        self.fm.writes = []
        self.st._render_frame(0.02)
        self.assertEqual(self.u2.get_channel(100), 0)            # freigegeben
        self.assertEqual(self.st._engine_extra_prev.get(2, set()), set())

    def test_engine_extra_isolated_per_universe(self):
        # Gleichzeitig je ein Roh-Kanal auf Univ 1 (ungepatchte Adresse) und Univ 2.
        self.fm.writes = [(1, 400, 111), (2, 50, 222)]
        self.st._render_frame(0.02)
        self.assertEqual(self.u1.get_channel(400), 111)
        self.assertEqual(self.u2.get_channel(50), 222)
        # Nur den Schreiber auf Univ 2 stoppen -> Univ 1 bleibt, Univ 2 frei.
        self.fm.writes = [(1, 400, 111)]
        self.st._render_frame(0.02)
        self.assertEqual(self.u1.get_channel(400), 111)          # weiter aktiv
        self.assertEqual(self.u2.get_channel(50), 0)             # nur hier freigegeben
        self.assertEqual(self.st._engine_extra_prev.get(1), {400})
        self.assertEqual(self.st._engine_extra_prev.get(2, set()), set())

    def test_raw_released_on_repatch_multi(self):
        # STAB-14 auch multi-universe: der Roh-Kanal auf Univ 2 wird beim Repatch
        # aktiv genullt (nicht als Zombie belassen), obwohl er nie gepatcht war.
        self.fm.writes = [(2, 100, 255)]
        self.st._render_frame(0.02)
        self.assertEqual(self.u2.get_channel(100), 255)
        self.fm.writes = []
        self.st._rebuild_render_plan()                           # Repatch
        self.assertEqual(self.u2.get_channel(100), 0)            # frei
        self.assertEqual(self.st._engine_extra_prev, {})


# ── (3) EE-02 Color-only ────────────────────────────────────────────────────
class ColorOnlyMultiplyTest(unittest.TestCase):
    """Ein Fixture OHNE eigenen Dimmer (nur RGB): ein reiner Farb-Effekt setzt
    color_r=200. Die Programmer-Intensitaet (128) multipliziert den Farb-Fallback-
    Dimmer -> ~100. Es wird KEINE separate Intensitaets-Adresse skaliert (das
    Fixture hat keine) — nur die vom Effekt getriebene Farbe wird gedimmt (EE-02)."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        # Reines RGB-Fixture: KEIN intensity/dimmer-Kanal.
        A.get_channels_for_patched = lambda fx: [
            _Ch("color_r", 1, 0), _Ch("color_g", 2, 0), _Ch("color_b", 3, 0),
        ]
        self.fm = _MultiFM()
        self.st = _make_state([1], self.fm, [_Fx(1, 1, 10)])   # RGB an Adressen 10..12
        self.st._rebuild_render_plan()
        self.live = self.st.universes[1]

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_color_effect_scaled_by_programmer_intensity(self):
        # Effekt faerbt color_r (Adresse 10) auf 200.
        self.fm.writes = [(1, 10, 200)]
        # Programmer-Intensitaet 128 -> Faktor 128/255 ~ 0.502.
        self.st.programmer = {1: {"intensity": 128}}
        self.st._render_frame(0.02)
        # Farb-Fallback-Dimmer: 200 * 128/255 = 100.4 -> 100 (EE-02-Multiply).
        self.assertEqual(self.live.get_channel(10), 100)

    def test_full_intensity_leaves_color_untouched(self):
        # Volle Programmer-Intensitaet (255) -> Faktor ~1.0, Farbe unveraendert.
        self.fm.writes = [(1, 10, 200)]
        self.st.programmer = {1: {"intensity": 255}}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 200)

    def test_no_separate_intensity_channel_written(self):
        # Das Fixture hat keinen Intensitaets-Kanal: der Programmer-intensity-Wert
        # erzeugt keine eigene Absolut-Schreibung, sondern wirkt NUR multiplikativ
        # auf die Farbe. Ohne Farb-Effekt bleibt bei color-only alles dunkel.
        self.fm.writes = []
        self.st.programmer = {1: {"intensity": 200}}
        self.st._render_frame(0.02)
        self.assertEqual(self.live.get_channel(10), 0)
        self.assertEqual(self.live.get_channel(11), 0)
        self.assertEqual(self.live.get_channel(12), 0)


if __name__ == "__main__":
    unittest.main()
