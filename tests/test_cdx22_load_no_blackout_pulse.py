"""CDX-22: Ein LIVE-Show-Load darf keinen Blackout-Puls auf den alten Adressen
erzeugen.

``load_show`` ist reset-first (STAB-19b) und ruft ``_reset_state`` mit
``blackout_output=False``, um genau diesen Puls zu vermeiden. Dieser Guard
ueberspringt aber nur den EXPLIZITEN ``universe.clear()``/``_flush_all_to_dmx()``
— NICHT die A3D-18-Freigabe entpatchter Adressen: der reset-first setzt einen
LEEREN Patch, und dessen ``_rebuild_render_plan`` sah JEDE bisher gepatchte
Adresse als "jetzt frei" und nullte sie sofort im Live-Universe. Der 44-Hz-
Output-Thread sendet diese Nullen physisch, bis der neue Patch geladen und
gerendert ist -> bei JEDEM Live-Load blitzt das Rig kurz schwarz.

Fix: ``AppState.deferred_unpatched_release`` buendelt die Freigabe ueber den
mehrstufigen Patch-Tausch (leerer Patch -> neuer Patch); ``load_show`` klammert
reset-first + Patch-Restore darin. Weiter gepatchte Adressen bleiben unberuehrt,
genuin entpatchte werden am Ende trotzdem freigegeben (A3D-18/CDX-17 intakt).
"""
import json
import os
import tempfile
import threading
import types
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

import src.core.app_state as A
from src.core.app_state import AppState, get_state
from src.core.database import fixture_db as fdb
from src.core.database.models import FixtureProfile, FixtureMode
from src.core.dmx.universe import Universe
from src.core.show.show_file import load_show


# ── Synthetischer State (Muster aus test_zombie_channel_release.py) ────────────

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

    def __init__(self, fid, universe, address, fixture_type=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = fixture_type


class _FM:
    def tick(self, universes, patch_cache, dt):
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


class DeferredReleaseUnitTest(unittest.TestCase):
    """Kern-Semantik des Deferral-Fensters direkt am Render-Plan."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = _chans

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_repatched_addr_never_zeroed_during_swap(self):
        st = _make_state([_Fx(5, 1, 10)])
        live = st.universes[1]
        for a in (10, 11, 12, 13):
            live.set_channel(a, 200)

        with st.deferred_unpatched_release():
            st._patch_cache = []                 # reset-first: leerer Patch
            st._rebuild_render_plan()
            for a in (10, 11, 12, 13):
                self.assertEqual(
                    live.get_channel(a), 200,
                    f"addr {a} im Deferral-Fenster genullt -> Blackout-Puls")
            self.assertFalse(st._pending_release.get(1),
                             "Adressen im Fenster vorgemerkt -> Render-Thread nullt sie")
            st._patch_cache = [_Fx(5, 1, 10)]    # neuer Patch, gleiche Adressen
            st._rebuild_render_plan()

        for a in (10, 11, 12, 13):
            self.assertEqual(live.get_channel(a), 200,
                             f"addr {a} nach dem Tausch genullt -> Blackout-Puls")
        self.assertFalse(st._pending_release.get(1),
                         "weiter gepatchte Adressen wurden zur Freigabe vorgemerkt")
        self.assertEqual(st._deferred_release, {}, "Deferral-Puffer nicht geleert")

    def test_genuinely_unpatched_addr_still_released_at_scope_exit(self):
        # A3D-18 bleibt intakt: was die NEUE Show nicht mehr patcht, wird freigegeben.
        st = _make_state([_Fx(5, 1, 10), _Fx(6, 1, 20)])
        live = st.universes[1]
        for a in (10, 11, 12, 13, 20, 21, 22, 23):
            live.set_channel(a, 200)

        with st.deferred_unpatched_release():
            st._patch_cache = []
            st._rebuild_render_plan()
            st._patch_cache = [_Fx(5, 1, 10)]    # fid6 fehlt in der neuen Show
            st._rebuild_render_plan()

        for a in (10, 11, 12, 13):
            self.assertEqual(live.get_channel(a), 200, f"addr {a} faelschlich genullt")
        for a in (20, 21, 22, 23):
            self.assertEqual(live.get_channel(a), 0,
                             f"addr {a} blieb Zombie (A3D-18 gebrochen)")
        # race-fest gegen nachlaufenden Alt-Plan-Commit: nur die echten Waisen.
        self.assertEqual(st._pending_release.get(1), {20, 21, 22, 23})

    def test_readdressed_fixture_releases_only_vacated_addrs(self):
        st = _make_state([_Fx(5, 1, 10)])
        live = st.universes[1]
        for a in (10, 11, 12, 13):
            live.set_channel(a, 200)

        with st.deferred_unpatched_release():
            st._patch_cache = []
            st._rebuild_render_plan()
            st._patch_cache = [_Fx(5, 1, 12)]    # verschoben -> 12..15
            st._rebuild_render_plan()

        self.assertEqual(live.get_channel(10), 0, "verlassene addr 10 nicht frei")
        self.assertEqual(live.get_channel(11), 0, "verlassene addr 11 nicht frei")
        self.assertEqual(live.get_channel(12), 200, "addr 12 faelschlich genullt")
        self.assertEqual(live.get_channel(13), 200, "addr 13 faelschlich genullt")

    def test_release_happens_even_if_swap_raises(self):
        st = _make_state([_Fx(5, 1, 10)])
        live = st.universes[1]
        for a in (10, 11, 12, 13):
            live.set_channel(a, 200)
        with self.assertRaises(RuntimeError):
            with st.deferred_unpatched_release():
                st._patch_cache = []
                st._rebuild_render_plan()
                raise RuntimeError("Patch-Restore geworfen")
        for a in (10, 11, 12, 13):
            self.assertEqual(live.get_channel(a), 0,
                             f"addr {a} blieb nach Abbruch Zombie")
        self.assertEqual(st._defer_release_depth, 0, "Deferral-Tiefe nicht abgebaut")

    def test_nested_scopes_release_once_at_outermost_exit(self):
        st = _make_state([_Fx(5, 1, 10)])
        live = st.universes[1]
        for a in (10, 11, 12, 13):
            live.set_channel(a, 200)
        with st.deferred_unpatched_release():
            with st.deferred_unpatched_release():
                st._patch_cache = []
                st._rebuild_render_plan()
            self.assertEqual(live.get_channel(10), 200,
                             "innerer Scope gab bereits frei (Tiefen-Zaehler defekt)")
        self.assertEqual(live.get_channel(10), 0, "aeusserer Scope gab nicht frei")

    def test_laser_addrs_are_never_deferred(self):
        # SAFETY: Das Fenster haelt alte Adressen absichtlich auf ihrem Wert. Fuer
        # DMX-LASER waere das falsch: solange der Plan sie nicht kennt, greift
        # weder die Renderer-Nullung noch die OutputManager-Maske eines JETZT
        # ausgeloesten NOT-AUS an sie -> Laser-Adressen sofort freigeben.
        st = _make_state([_Fx(5, 1, 10), _Fx(7, 1, 30, fixture_type="laser")])
        live = st.universes[1]
        self.assertEqual(st._laser_estop_addrs.get(1), frozenset({30, 31, 32, 33}),
                         "Laser-Adressen nicht als Laser erkannt")
        for a in (10, 11, 12, 13, 30, 31, 32, 33):
            live.set_channel(a, 200)

        with st.deferred_unpatched_release():
            st._patch_cache = []
            st._rebuild_render_plan()
            for a in (30, 31, 32, 33):
                self.assertEqual(live.get_channel(a), 0,
                                 f"Laser-addr {a} im Fenster nicht freigegeben")
            for a in (10, 11, 12, 13):
                self.assertEqual(live.get_channel(a), 200,
                                 f"Nicht-Laser-addr {a} faelschlich genullt")
            st._patch_cache = [_Fx(5, 1, 10), _Fx(7, 1, 30, fixture_type="laser")]
            st._rebuild_render_plan()

        for a in (10, 11, 12, 13):
            self.assertEqual(live.get_channel(a), 200,
                             f"addr {a} nach dem Tausch genullt -> Blackout-Puls")

    def test_direct_rebuild_without_scope_unchanged(self):
        # Ohne Fenster bleibt das A3D-18-Verhalten byte-identisch (Sofort-Freigabe).
        st = _make_state([_Fx(5, 1, 10)])
        live = st.universes[1]
        for a in (10, 11, 12, 13):
            live.set_channel(a, 200)
        st._patch_cache = []
        st._rebuild_render_plan()
        for a in (10, 11, 12, 13):
            self.assertEqual(live.get_channel(a), 0)
        self.assertEqual(st._pending_release.get(1), {10, 11, 12, 13})


class ClearProgrammerFlushGateTest(unittest.TestCase):
    """``flush=False`` ist NUR fuer den Ladepfad — der normale Programmer-Clear
    (Taste „Clear", VC, Web/OSC, Kommandozeile) muss weiter sofort flushen."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = _chans

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_default_clear_programmer_still_flushes_to_dmx(self):
        st = _make_state([_Fx(5, 1, 10)])
        live = st.universes[1]
        st.programmer = {5: {"intensity": 200}}
        st._flush_all_to_dmx()
        self.assertEqual(live.get_channel(10), 200, "Vorbedingung: Flush schrieb nicht")
        st.clear_programmer()
        self.assertEqual(live.get_channel(10), 0,
                         "Default-Clear flusht nicht mehr -> Werte haengen im Output")
        self.assertEqual(st.programmer, {})

    def test_clear_programmer_no_flush_keeps_live_values(self):
        st = _make_state([_Fx(5, 1, 10)])
        live = st.universes[1]
        st.programmer = {5: {"intensity": 200}}
        st._flush_all_to_dmx()
        st.clear_programmer(flush=False)
        self.assertEqual(live.get_channel(10), 200,
                         "flush=False hat trotzdem in die Ausgabe geschrieben")
        self.assertEqual(st.programmer, {}, "In-Memory-Clear ist nicht passiert")


# ── Ende-zu-Ende ueber load_show (echter Repro-Pfad) ──────────────────────────

_ADDR = 21          # dimmer -> 21, fan -> 22


def _euron10_profile():
    """(profile_id, 2-Kanal-Mode-Name, channel_count) des Builtin-EURON10."""
    fdb.ensure_builtins()
    with Session(fdb.engine()) as s:
        prof = s.execute(
            select(FixtureProfile)
            .options(selectinload(FixtureProfile.modes).selectinload(FixtureMode.channels))
            .where(FixtureProfile.short_name == "EURON10")
        ).scalars().first()
        m2 = next(m for m in prof.modes if m.name.startswith("2-Kanal"))
        return prof.id, m2.name, len(m2.channels)


def _show(pid, mode, cc, *, with_patch: bool = True) -> dict:
    patch = [{
        "fid": 1, "label": "Fog", "fixture_profile_id": pid, "mode_name": mode,
        "universe": 1, "address": _ADDR, "channel_count": cc,
        "fixture_name": "N-10 Nebelmaschine", "manufacturer_name": "Eurolite",
        "fixture_type": "hazer",
    }] if with_patch else []
    return {"version": "1.2", "patch": patch,
            "programmer": {"1": {"dimmer": 200}} if with_patch else {}}


def _write(show: dict) -> str:
    path = os.path.join(tempfile.mkdtemp(), "cdx22.lshow")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("show.json", json.dumps(show))
    return path


class LoadShowNoPulseTest(unittest.TestCase):
    """Der echte Pfad: zweiter Live-Load derselben Adressen darf sie nie nullen."""

    def setUp(self):
        os.environ.pop("LIGHTOS_STRICT", None)
        self.pid, self.mode, self.cc = _euron10_profile()
        ok, msg = load_show(_write(_show(self.pid, self.mode, self.cc)))
        self.assertTrue(ok, msg)
        st = get_state()
        self.uni = st.universes.get(1)
        self.assertIsNotNone(self.uni, "Universe 1 nach dem Patch-Load nicht da")
        self.assertEqual(self.uni.get_channel(_ADDR), 200,
                         "Baseline: Dimmer-Adresse steht nicht auf 200")
        # _pending_release konsumiert nur _render_frame; ohne laufenden Render-
        # Thread traegt der Test-Prozess Reste voriger Tests/Loads weiter. Baseline
        # bewusst leeren, damit die Assertions unten nur DIESEN Load bewerten.
        st._pending_release.clear()

    def _record_zero_writes(self):
        """Zeichnet JEDEN Schreibvorgang mit Wert 0 auf dem Live-Universe auf.
        Der Puls ist nur so nachweisbar: der Programmer-Flush am Ende des Loads
        setzt die Adresse ohnehin wieder auf 200, der physische 0-Frame ging da
        aber schon raus."""
        zeros: list[int] = []
        orig = self.uni.set_channel

        def _rec(channel, value):
            if int(value) == 0:
                zeros.append(int(channel))
            return orig(channel, value)

        self.uni.set_channel = _rec
        # Instanz-Attribut wieder entfernen -> die Klassen-Methode greift erneut.
        self.addCleanup(lambda: self.uni.__dict__.pop("set_channel", None))
        return zeros

    def test_second_load_same_patch_no_zero_write(self):
        zeros = self._record_zero_writes()
        ok, msg = load_show(_write(_show(self.pid, self.mode, self.cc)))
        self.assertTrue(ok, msg)
        self.assertNotIn(_ADDR, zeros,
                         "Dimmer-Adresse wurde beim Live-Load auf 0 geschrieben "
                         "-> Blackout-Puls (CDX-22)")
        self.assertNotIn(_ADDR + 1, zeros,
                         "Fan-Adresse wurde beim Live-Load auf 0 geschrieben "
                         "-> Blackout-Puls (CDX-22)")
        st = get_state()
        self.assertEqual(self.uni.get_channel(_ADDR), 200)
        self.assertFalse(st._pending_release.get(1),
                         "weiter gepatchte Adressen zur Render-Freigabe vorgemerkt")

    def test_load_show_without_that_fixture_releases_addr(self):
        # Gegenprobe: patcht die neue Show das Fixture NICHT mehr, muss die
        # Adresse freigegeben werden (sonst Zombie-Nebel/-Dimmer auf der Buehne).
        ok, msg = load_show(_write(_show(self.pid, self.mode, self.cc, with_patch=False)))
        self.assertTrue(ok, msg)
        self.assertEqual(self.uni.get_channel(_ADDR), 0,
                         "entpatchte Adresse blieb Zombie (A3D-18 gebrochen)")
        st = get_state()
        self.assertIn(_ADDR, st._pending_release.get(1, set()),
                      "entpatchte Adresse nicht fuer den Render-Thread vorgemerkt")


if __name__ == "__main__":
    unittest.main()
