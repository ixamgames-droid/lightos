"""ENG-11 — Mehrkopf-``attr#N`` muss durch alle Kernpfade konsistent bleiben."""
from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import (
    channel_occurrence_keys, get_channels_for_patched, get_state,
)
from src.core.attr_groups import attr_label, classify_attr
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import FixtureProfile, PatchedFixture
from src.core.engine.mapped_channel import (
    MappedChannelChange, MappedRule, SOURCE_PAN,
)
from src.core.engine.palette import Palette, PaletteType
from src.core.show.show_file import load_show, reset_show, save_show
from src.ui.views.programmer_view import programmer_to_scene_values


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _profile_id(short_name: str) -> int:
    with Session(fdb_engine()) as session:
        return int(session.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short_name
        )).scalar_one())


class MultiHeadAttributeSweep(unittest.TestCase):
    """MOVBAR4 liefert vier echte Pan-/Tilt-/RGB-Koepfe statt Test-Dummies."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1,
            label="Sweep Bar",
            fixture_profile_id=_profile_id("MOVBAR4"),
            mode_name="22-Kanal 4×Move RGB",
            universe=1,
            address=1,
            channel_count=22,
            manufacturer_name="Generic",
            fixture_name="LED Moving Bar 4×",
            fixture_type="moving_head",
        ), undoable=False)
        self.state._rebuild_render_plan()
        self.fixture = next(f for f in self.state.get_patched_fixtures() if f.fid == 1)
        self.channels = get_channels_for_patched(self.fixture)
        if 1 not in self.state.universes:
            self.state.universes[1] = self.state.output_manager.add_universe(1)
        self.universe = self.state.universes[1]

    def _channel_numbers(self, attribute: str) -> list[int]:
        return [ch.channel_number for ch, key in channel_occurrence_keys(self.channels)
                if key == attribute or key.startswith(attribute + "#")]

    def test_set_get_classify_and_scene_keep_all_four_heads(self):
        values = [31, 62, 93, 124]
        for head, value in enumerate(values):
            self.state.set_programmer_value(1, "color_r", value, head=head)
            self.assertEqual(self.state.get_programmer_value(1, "color_r", head=head), value)

        keys = [key for _ch, key in channel_occurrence_keys(self.channels)
                if key == "color_r" or key.startswith("color_r#")]
        self.assertEqual(keys, ["color_r", "color_r#1", "color_r#2", "color_r#3"])
        self.assertEqual(classify_attr("color_r#3"), "Color")
        self.assertEqual(attr_label("color_r#3"), "Rot (Kopf 4)")

        scene_values = programmer_to_scene_values(self.state.programmer, [self.fixture])
        by_channel = {channel: value for _fid, channel, value in scene_values}
        self.assertEqual(
            [by_channel[channel] for channel in self._channel_numbers("color_r")], values
        )

    def test_palette_apply_and_record_preserve_per_head_values(self):
        values = {"color_r": 10, "color_r#1": 20, "color_r#2": 30, "color_r#3": 40}
        palette = Palette("Bar heads", PaletteType.COLOR, fixture_values={1: values})
        palette.apply_to_programmer([1])
        self.assertEqual(self.state.programmer[1], values)

        recorded = Palette("Record", PaletteType.COLOR)
        recorded.record_from_programmer([1])
        self.assertEqual(recorded.fixture_values[1], values)

    def test_show_roundtrip_preserves_head_keys(self):
        values = {"color_r": 11, "color_r#1": 22, "color_r#2": 33, "color_r#3": 44}
        self.state.programmer[1] = dict(values)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "heads.lshow")
            save_show(path)
            self.state.clear_programmer()
            ok, message = load_show(path)
        self.assertTrue(ok, message)
        self.assertEqual(self.state.programmer.get(1), values)

    def test_mapped_channel_base_value_mirrors_every_head(self):
        """ENG-11: Ein nicht-per-head Mapping darf nicht nur Kopf 0 erreichen."""
        pan_channels = self._channel_numbers("pan")
        color_channels = self._channel_numbers("color_r")
        self.assertEqual(len(pan_channels), 4)
        self.assertEqual(len(color_channels), 4)
        self.universe.set_channel(pan_channels[0], 73)

        mapped = MappedChannelChange("Mirror")
        mapped.fids = [1]
        mapped.rules = [MappedRule(source=SOURCE_PAN, target="color_r", per_head=False)]
        mapped._running = True
        mapped.write(self.state.universes, [self.fixture], 0.0)

        self.assertEqual(
            [self.universe.get_channel(channel) for channel in color_channels],
            [73, 73, 73, 73],
        )

    def test_mapped_channel_per_head_keeps_independent_values(self):
        pan_channels = self._channel_numbers("pan")
        color_channels = self._channel_numbers("color_r")
        values = [25, 75, 125, 175]
        for channel, value in zip(pan_channels, values):
            self.universe.set_channel(channel, value)

        mapped = MappedChannelChange("Independent")
        mapped.fids = [1]
        mapped.rules = [MappedRule(source=SOURCE_PAN, target="color_r", per_head=True)]
        mapped._running = True
        mapped.write(self.state.universes, [self.fixture], 0.0)

        self.assertEqual(
            [self.universe.get_channel(channel) for channel in color_channels], values
        )


if __name__ == "__main__":
    unittest.main()
