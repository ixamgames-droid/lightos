"""CDX-22b: auch script-getriebene ROH-Adressen dürfen beim Live-Load nicht blitzen.

CDX-22 hat den Blackout-Puls für **gepatchte** Adressen beseitigt: ``load_show``
setzt reset-first einen leeren Patch, und dessen Rebuild sah jede bisherige
Adresse als „jetzt frei". Eine Ebene tiefer blieb dasselbe Problem stehen —
``_release_engine_extra`` nullte die zuletzt per ``ScriptFunction.setdmx``
getriebenen, NICHT gepatchten Adressen sofort, mitten im Ladefenster.

Gemessen vor dem Fix (mit demselben Aufbau wie hier): Roh-Kanal 100 fiel im
Fenster von 200 auf 0 — und blieb dort, obwohl die neue Show dieselbe Adresse
treibt. Der 44-Hz-Output-Thread sendet diese Null physisch.

Der Fix darf STAB-14 nicht rückgängig machen. Deshalb prüfen diese Tests beide
Richtungen: kein Puls, wenn jemand die Adresse weiter treibt — und weiterhin
**Freigabe**, wenn niemand sie mehr treibt. Ohne die zweite Hälfte wäre der Fix
eine Rückkehr des Zombies, den STAB-14 beseitigt hat (bei Strobe/Shutter/Beam
sicht- und sicherheitsrelevant).
"""
import os
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A                                      # noqa: E402
from src.core.app_state import AppState                             # noqa: E402
from src.core.dmx.universe import Universe                          # noqa: E402


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4
    protocol = ""

    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = ""


class _FM:
    def tick(self, *a):
        pass


def _chans(_fx):
    return [_Ch("intensity", 1), _Ch("color_r", 2),
            _Ch("color_g", 3), _Ch("color_b", 4)]


def _make_state(patch):
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = list(patch)
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st._rebuild_render_plan()
    return st


class EngineExtraDeferralTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = _chans

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _mit_rohkanal(self, adresse=100, wert=200):
        """State, in dem ein Skript ``adresse`` (ungepatcht) auf ``wert`` treibt."""
        st = _make_state([_Fx(5, 1, 10)])
        st.universes[1].set_channel(adresse, wert)
        st._engine_extra_prev = {1: {adresse}}
        return st

    def test_kein_puls_wenn_die_neue_show_dieselbe_rohadresse_treibt(self):
        st = self._mit_rohkanal()
        live = st.universes[1]

        with st.deferred_unpatched_release():
            st._patch_cache = []                       # reset-first: leerer Patch
            st._rebuild_render_plan()
            self.assertEqual(live.get_channel(100), 200,
                             "Roh-Kanal im Ladefenster genullt -> Blackout-Puls")
            st._patch_cache = [_Fx(5, 1, 10)]
            st._rebuild_render_plan()
            # der Renderer der neuen Show hat die Adresse wieder als Extra gemeldet
            st._engine_extra_prev = {1: {100}}

        self.assertEqual(live.get_channel(100), 200,
                         "Roh-Kanal nach dem Tausch genullt -> Puls")

    def test_stab14_bleibt_intakt_verwaiste_rohadresse_wird_freigegeben(self):
        """Die wichtigere Hälfte: treibt sie NIEMAND mehr, muss sie aus."""
        st = self._mit_rohkanal()
        live = st.universes[1]

        with st.deferred_unpatched_release():
            st._patch_cache = []
            st._rebuild_render_plan()
            st._patch_cache = [_Fx(5, 1, 10)]
            st._rebuild_render_plan()
            # die neue Show treibt die Adresse NICHT — _engine_extra_prev bleibt leer

        self.assertEqual(live.get_channel(100), 0,
                         "verwaister Roh-Kanal blieb an -> Zombie, STAB-14 kaputt")

    def test_inzwischen_gepatchte_rohadresse_wird_nicht_genullt(self):
        """Deckt die neue Show die Adresse mit einem Fixture ab, committet sie ihr
        Span — die Roh-Ebene darf da nicht dazwischenfunken."""
        st = self._mit_rohkanal(adresse=20)
        live = st.universes[1]

        with st.deferred_unpatched_release():
            st._patch_cache = []
            st._rebuild_render_plan()
            st._patch_cache = [_Fx(5, 1, 10), _Fx(7, 1, 20)]   # 20 ist jetzt gepatcht
            st._rebuild_render_plan()

        self.assertEqual(live.get_channel(20), 200,
                         "gepatchte Adresse von der Roh-Freigabe genullt")

    def test_ohne_fenster_wird_weiter_sofort_freigegeben(self):
        """Ausserhalb eines Ladefensters bleibt STAB-14 unveraendert sofort."""
        st = self._mit_rohkanal()
        live = st.universes[1]
        st._patch_cache = []
        st._rebuild_render_plan()
        self.assertEqual(live.get_channel(100), 0,
                         "Sofort-Freigabe ausserhalb des Fensters ausgefallen")

    def test_ausnahme_im_fenster_gibt_trotzdem_frei(self):
        """Sonst haenge der Roh-Kanal nach einem gescheiterten Load fuer immer."""
        st = self._mit_rohkanal()
        live = st.universes[1]

        class Geplatzt(Exception):
            pass

        with self.assertRaises(Geplatzt):
            with st.deferred_unpatched_release():
                st._patch_cache = []
                st._rebuild_render_plan()
                raise Geplatzt()

        self.assertEqual(live.get_channel(100), 0,
                         "nach Ausnahme im Ladefenster nicht freigegeben")
        self.assertEqual(st._deferred_engine_extra, {}, "Puffer nicht geleert")

    def test_nur_die_aeusserste_ebene_gibt_frei(self):
        """Verschachtelte Fenster: eine innere Ebene darf nicht vorzeitig nullen."""
        st = self._mit_rohkanal()
        live = st.universes[1]

        with st.deferred_unpatched_release():
            with st.deferred_unpatched_release():
                st._patch_cache = []
                st._rebuild_render_plan()
            self.assertEqual(live.get_channel(100), 200,
                             "innere Ebene hat schon freigegeben -> Puls")
            st._patch_cache = [_Fx(5, 1, 10)]
            st._rebuild_render_plan()

        self.assertEqual(live.get_channel(100), 0)

    def test_mehrere_rebuilds_im_fenster_verlieren_keine_adresse(self):
        """Der Puffer sammelt ueber ALLE Rebuilds im Fenster — sonst faellt eine
        Adresse aus der Freigabe, sobald der Load mehr als zwei Stufen hat."""
        st = _make_state([_Fx(5, 1, 10)])
        live = st.universes[1]
        for a in (100, 101):
            live.set_channel(a, 200)

        with st.deferred_unpatched_release():
            st._engine_extra_prev = {1: {100}}
            st._rebuild_render_plan()
            st._engine_extra_prev = {1: {101}}
            st._rebuild_render_plan()

        self.assertEqual((live.get_channel(100), live.get_channel(101)), (0, 0),
                         "eine Adresse aus einem frueheren Rebuild ging verloren")


if __name__ == "__main__":
    unittest.main()
