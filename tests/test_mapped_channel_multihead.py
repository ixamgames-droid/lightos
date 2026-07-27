"""MappedChannelChange.write muss ALLE Koepfe erreichen, nicht nur den ersten.

Geborgen 2026-07-26 aus dem nie gemergten Branch `fix/multihead-attribute-sweep`
(Triage der Alt-Branches). Der dortige Befund war ein echter, ungelandeter Bug:
`mapped_channel.write` hatte den Basiswert-Fallback auf `head == 0` gegattert, ein
Mapping mit ``per_head=False`` erreichte auf einem Mehrkopf-Fixture also nur die
erste RGB-Bank ([73, 0, 0, 0] statt [73, 73, 73, 73]).

Warum das wehtut: ``per_head=False`` ist der **Default** jeder neu angelegten Regel
(`MappedRule.per_head`), und Davids Rig hat Mehrkopf-Geraete (Hydrabeam 4000 = 4
Koepfe). ENG-11 hatte den attr#N-Pfad zwar gesweept, aber genau `mapped_channel`
nicht abgedeckt — es gab auf main NULL Tests fuer `MappedChannelChange.write`.

Bewusst eine EIGENE Datei statt der gleichnamigen `test_multihead_sweep.py` des
Branches: die main-Fassung dieser Datei ist breiter und darf nicht ueberschrieben
werden.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import (
    channel_occurrence_keys, get_channels_for_patched, get_state,
)
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import FixtureProfile, PatchedFixture
from src.core.engine.mapped_channel import (
    MappedChannelChange, MappedRule, SOURCE_PAN,
)
from src.core.show.show_file import reset_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _profile_id(short_name: str) -> int:
    with Session(fdb_engine()) as session:
        return int(session.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short_name
        )).scalar_one())


class MappedChannelMultiHeadTest(unittest.TestCase):
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
        """Gegenprobe: per_head=True darf die Koepfe NICHT gleichschalten."""
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
