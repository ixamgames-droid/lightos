"""Mehrkopf (X-6): Pro-Kopf-Werte ueberleben SAVE und PLAYBACK (Sequence + Szene).

Regression fuer den Bug, dass die Value->Kanal-Aufloesung in den Speicher-/
Wiedergabe-Pfaden die ``"attr#N"``-Vorkommens-Logik (wie in
``_flush_programmer_to_dmx``/``efx.py``) NICHT kannte:

  1. ``sequence.py`` matchte nur ``ch.attribute in attrs`` -> ``"color_r#1"`` wurde
     nie getroffen, beide Spider-Bars zeigten nur die Kopf-0-Farbe.
  2. ``programmer_to_scene_values`` baute ein ``{attribute: channel}``-Dict, das bei
     zwei ``color_r`` KOLLIDIERTE: ``color_r#1`` verfiel UND der Kopf-0-Wert rutschte
     auf den ZWEITEN Kanal (CH6 blieb leer).
  3. ``Chaser.capture_step`` (Programmer -> Scene.set_value) hatte dieselbe Luecke.

SPIDER14: zwei RGBW-Baenke -> ``color_r`` an CH6 (Bank 1) UND CH10 (Bank 2).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import (
    get_state, get_channels_for_patched, resolve_attr_channels)
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show
from src.core.engine.sequence import Sequence, SequenceStep
from src.core.engine.scene import Scene
from src.ui.views.programmer_view import programmer_to_scene_values


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class MultiHeadSaveReplayTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=1, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head"), undoable=False)
        self.state._rebuild_render_plan()
        u = self.state.universes.get(1)
        if u is None:
            u = self.state.output_manager.add_universe(1)
            self.state.universes[1] = u
        self.u = self.state.universes[1]
        self.fx = next(f for f in self.state.get_patched_fixtures() if f.fid == 1)

    # ── Sanity: das Profil hat color_r wirklich doppelt (CH6 + CH10) ──────────
    def test_spider_has_two_color_r_banks(self):
        cols = [c.channel_number for c in get_channels_for_patched(self.fx)
                if (c.attribute or "") == "color_r"]
        self.assertEqual(cols, [6, 10])

    # ── Helper-Einheit: Vorkommens-Aufloesung ─────────────────────────────────
    def test_resolve_attr_channels_per_head(self):
        chans = get_channels_for_patched(self.fx)
        res = resolve_attr_channels(chans, {"color_r": 200, "color_r#1": 50})
        got = {cn: v for cn, k, v in res if k.startswith("color_r")}
        self.assertEqual(got.get(6), 200)
        self.assertEqual(got.get(10), 50)

    def test_resolve_attr_channels_head0_mirrors(self):
        # Nur Kopf 0 gesetzt -> Kopf 1 spiegelt (Fallback auf schlichten Namen).
        chans = get_channels_for_patched(self.fx)
        res = resolve_attr_channels(chans, {"color_r": 180})
        got = {cn: v for cn, k, v in res if k == "color_r"}
        self.assertEqual(got.get(6), 180)
        self.assertEqual(got.get(10), 180)

    # ── Punkt 1: Sequence (Chase aus Snaps) spielt beide Bars getrennt ────────
    def test_sequence_replays_both_bars_separately(self):
        seq = Sequence("Spider Seq")
        seq.bound_fixtures = [1]
        seq.steps = [SequenceStep(
            values={"1": {"color_r": 200, "color_r#1": 50}},
            fade_in=0.0, hold=1.0, fade_out=0.0)]
        seq._on_start()
        seq._running = True
        seq.write(self.state.universes, self.state.get_patched_fixtures(), 0.0)
        self.assertEqual(self.u.get_channel(6), 200)   # Bank 1
        self.assertEqual(self.u.get_channel(10), 50)   # Bank 2 (war: 200/0)

    def test_sequence_head0_mirrors_to_both_bars(self):
        seq = Sequence("Spider Seq")
        seq.bound_fixtures = [1]
        seq.steps = [SequenceStep(
            values={"1": {"color_r": 90}}, fade_in=0.0, hold=1.0, fade_out=0.0)]
        seq._on_start()
        seq._running = True
        seq.write(self.state.universes, self.state.get_patched_fixtures(), 0.0)
        self.assertEqual(self.u.get_channel(6), 90)
        self.assertEqual(self.u.get_channel(10), 90)

    # ── Punkt 2: Programmer -> Scene-Werte (Speicher-Bruecke) ─────────────────
    def test_programmer_to_scene_values_per_head(self):
        vals = programmer_to_scene_values(
            {1: {"color_r": 200, "color_r#1": 50}},
            self.state.get_patched_fixtures())
        d = {(fid, ch): v for fid, ch, v in vals}
        self.assertEqual(d.get((1, 6)), 200)
        self.assertEqual(d.get((1, 10)), 50)

    def test_programmer_to_scene_values_head0_no_slip_to_ch10(self):
        # VORBESTEHENDER Spider-Bug: nur "color_r" gesetzt -> frueher fehlte CH6
        # ganz und CH10 bekam den Wert. Jetzt: BEIDE Kanaele bekommen ihn.
        vals = programmer_to_scene_values(
            {1: {"color_r": 180}}, self.state.get_patched_fixtures())
        d = {(fid, ch): v for fid, ch, v in vals}
        self.assertEqual(d.get((1, 6)), 180)
        self.assertEqual(d.get((1, 10)), 180)

    # ── Punkt 2 (end-to-end): die fertige Szene spielt beide Bars getrennt ────
    def test_scene_replays_both_bars_separately(self):
        vals = programmer_to_scene_values(
            {1: {"color_r": 200, "color_r#1": 50}},
            self.state.get_patched_fixtures())
        scene = Scene("Spider Scene")
        for fid, ch, v in vals:
            scene.set_value(fid, ch, v)
        self.u.set_channel(6, 0)
        self.u.set_channel(10, 0)
        scene._on_start()
        scene._running = True
        scene.write(self.state.universes, self.state.get_patched_fixtures(), 0.0)
        self.assertEqual(self.u.get_channel(6), 200)
        self.assertEqual(self.u.get_channel(10), 50)

    # ── Punkt 3: Chaser.capture_step (Programmer -> Scene.set_value) ──────────
    def test_chaser_capture_step_per_head(self):
        from src.core.engine.chaser import Chaser  # noqa: F401 (Typ-Doku)
        self.state.set_programmer_value(1, "color_r", 200, head=0)
        self.state.set_programmer_value(1, "color_r", 50, head=1)
        fm = self.state.function_manager
        chaser = fm.new_chaser("Cap")
        idx = chaser.capture_step()
        self.assertIsNotNone(idx)
        scene = fm.get(chaser.steps[idx].function_id)
        d = {(sv.fixture_id, sv.channel): sv.value for sv in scene.values}
        self.assertEqual(d.get((1, 6)), 200)
        self.assertEqual(d.get((1, 10)), 50)


if __name__ == "__main__":
    unittest.main()
