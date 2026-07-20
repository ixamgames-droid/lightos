"""STAB-19b: load_show ist RESET-FIRST — ein Crash mitten im Laden hinterlaesst
keinen halb-alten (Frankenstein) Zustand; und der reset-first-Pfad ist „still"
(kein Doppel-Emit, kein DMX-Blackout-Puls, keine Media-Player-Signale).
"""
import json
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state
from src.core.show.show_file import load_show, _reset_state
from src.core.engine.cue_stack import CueStack
from src.core.engine.snap_library import get_snap_library


def _lshow(show: dict) -> str:
    path = os.path.join(tempfile.mkdtemp(), "s.lshow")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("show.json", json.dumps(show))
    return path


def _show(name: str, with_programmer: bool = False) -> dict:
    # cue_stack UND snap tragen denselben Sentinel-Namen — beide werden NACH dem
    # efx_paths-Crash-Punkt geladen und sind damit diskriminierend fuer reset-first.
    d = {
        "version": "1.2", "patch": [],
        "cue_stacks": [CueStack(name).to_dict()],
        "library": {"folders": [], "snaps": [
            {"id": 1, "name": name, "folder": "", "values": {}}]},
    }
    if with_programmer:
        d["programmer"] = {"99": {"dimmer": 5}}
    return d


class TestStab19bLoadAtomic(unittest.TestCase):

    def test_crash_mid_load_no_frankenstein(self):
        os.environ.pop("LIGHTOS_STRICT", None)
        ok, _ = load_show(_lshow(_show("SENTINEL_A", with_programmer=True)))
        self.assertTrue(ok)
        st = get_state()
        self.assertEqual([s.name for s in st.cue_stacks], ["SENTINEL_A"])
        self.assertEqual([s.name for s in get_snap_library().snaps()], ["SENTINEL_A"])

        # STRICT (jeder _lenient-Block re-raised) + Crash im efx_paths-Block, der
        # VOR den cue_stacks- UND snap-Bloecken geladen wird.
        os.environ["LIGHTOS_STRICT"] = "1"
        self.addCleanup(lambda: os.environ.pop("LIGHTOS_STRICT", None))
        import src.core.engine.efx_path as efxmod
        orig = efxmod.get_efx_path_library
        self.addCleanup(lambda: setattr(efxmod, "get_efx_path_library", orig))

        def _boom(*a, **k):
            raise RuntimeError("injizierter Crash im efx_paths-Block")
        efxmod.get_efx_path_library = _boom

        try:
            load_show(_lshow(_show("SENTINEL_B")))
        except Exception:
            pass

        st = get_state()
        # cue_stacks UND snaps werden NACH efx_paths geladen: reset-first hat sie
        # geleert, der Crash brach VOR dem Reload ab -> LEER, NICHT Show A. Ohne
        # reset-first waeren beide noch 'SENTINEL_A' (Frankenstein).
        self.assertEqual([s.name for s in st.cue_stacks], [],
                         "cue_stacks der Show A ueberlebten den Crash -> Frankenstein")
        self.assertEqual([s.name for s in get_snap_library().snaps()], [],
                         "snaps der Show A ueberlebten den Crash -> Frankenstein")

    def test_reset_state_clears_loaded_fields_mirror_guard(self):
        os.environ.pop("LIGHTOS_STRICT", None)
        ok, _ = load_show(_lshow(_show("SENTINEL_A", with_programmer=True)))
        self.assertTrue(ok)
        st = get_state()
        self.assertTrue(st.cue_stacks and 99 in st.programmer and get_snap_library().snaps())

        _reset_state(st, emit_events=False, blackout_output=False)

        self.assertEqual(st.cue_stacks, [])
        self.assertEqual(st.programmer, {})
        self.assertEqual(st.fixture_dimmers, {})
        self.assertEqual(get_snap_library().snaps(), [])
        fm = getattr(st, "function_manager", None)
        if fm is not None:
            self.assertEqual(fm.all(), [])

    def test_partial_reset_crash_still_clears_later_fields(self):
        # F3: wirft eine fruehe (bare) Zeile in _reset_state, duerfen die spaeteren
        # Felder trotzdem geleert werden (die Kapselung faengt den Wurf, der Reset
        # laeuft weiter) — sonst blieben sie ALT = Frankenstein.
        os.environ.pop("LIGHTOS_STRICT", None)
        ok, _ = load_show(_lshow(_show("SENTINEL_A")))
        self.assertTrue(ok)
        st = get_state()
        self.assertTrue(st.cue_stacks)

        orig = st.clear_feature_dimmers
        self.addCleanup(lambda: setattr(st, "clear_feature_dimmers", orig))
        def _boom():
            raise RuntimeError("injizierter Crash in clear_feature_dimmers")
        st.clear_feature_dimmers = _boom

        _reset_state(st, emit_events=False, blackout_output=False)
        # cue_stacks werden NACH clear_feature_dimmers geleert -> trotz des Wurfs leer.
        self.assertEqual(st.cue_stacks, [],
                         "ein Wurf in clear_feature_dimmers verschluckte den Rest des Resets")

    def test_blackout_output_gates_dmx_blank(self):
        # F2: der Blackout-Puls entsteht durch universe.clear(). blackout_output=
        # False (load-first) darf den DMX-Puffer NICHT nullen (alte Werte bleiben
        # stehen, bis der neue Patch-Render sie setzt); =True (reset_show) blankt.
        os.environ.pop("LIGHTOS_STRICT", None)
        st = get_state()
        if not getattr(st, "universes", None):
            self.skipTest("kein Universe verfuegbar")
        univ = next(iter(st.universes.values()))
        univ.set_channel(1, 200)
        _reset_state(st, emit_events=False, blackout_output=False)
        self.assertEqual(univ.get_channel(1), 200,
                         "blackout_output=False hat die DMX-Ausgabe geblankt (Blackout-Puls)")
        univ.set_channel(1, 200)
        _reset_state(st, emit_events=False, blackout_output=True)
        self.assertEqual(univ.get_channel(1), 0,
                         "blackout_output=True hat den Puffer NICHT geblankt")

    def test_media_player_silent_during_reset_first(self):
        # F1: beim reset-first (emit_events=False) darf set_tracks() KEIN
        # playlistChanged feuern (blockSignals) -> kein UI-Rebuild mitten im Laden.
        os.environ.pop("LIGHTOS_STRICT", None)
        from src.core.audio.media_player import get_media_player
        mp = get_media_player()
        st = get_state()
        n = {"c": 0}

        def _slot(*a):
            n["c"] += 1
        mp.playlistChanged.connect(_slot)
        try:
            _reset_state(st, emit_events=False, blackout_output=False)
        finally:
            try:
                mp.playlistChanged.disconnect(_slot)
            except Exception:
                pass
        self.assertEqual(n["c"], 0, "playlistChanged feuerte im reset-first (blockSignals fehlt)")

    def test_normal_load_still_works(self):
        os.environ.pop("LIGHTOS_STRICT", None)
        ok, _ = load_show(_lshow(_show("SENTINEL_A")))
        self.assertTrue(ok)
        ok2, _ = load_show(_lshow(_show("SENTINEL_B")))
        self.assertTrue(ok2)
        st = get_state()
        self.assertEqual([s.name for s in st.cue_stacks], ["SENTINEL_B"])


if __name__ == "__main__":
    unittest.main()
