"""QA-LIVE: Der Fixture-Editor darf unsichtbare Profilmetadaten nicht loeschen."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.core.database.fixture_db import get_engine
from src.core.database.models import (
    ChannelRange, FixtureChannel, FixtureMode, FixtureProfile, Manufacturer,
    create_all_idempotent,
)
from src.ui.widgets import fixture_editor as editor_module


_app = QApplication.instance() or QApplication([])


def _load(session, fixture_id):
    return session.execute(
        select(FixtureProfile)
        .options(
            selectinload(FixtureProfile.modes)
            .selectinload(FixtureMode.channels)
            .selectinload(FixtureChannel.ranges),
        )
        .where(FixtureProfile.id == fixture_id)
    ).scalars().one()


class FixtureEditorRoundtripTest(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        with Session(self.engine) as session:
            maker = Manufacturer(name="Roundtrip Maker", short_name="RTM")
            profile = FixtureProfile(
                manufacturer=maker, name="Roundtrip Fixture", short_name="ROUND",
                fixture_type="moving_head", power_w=120, notes="Wichtige Notiz",
                source="user",
            )
            mode = FixtureMode(fixture=profile, name="Extended", channel_count=1,
                               description="Modus-Beschreibung")
            channel = FixtureChannel(
                mode=mode, channel_number=1, name="Pan fine", attribute="pan_fine",
                default_value=12, highlight_value=200, invert=True, resolution="16bit",
            )
            channel.ranges.append(ChannelRange(
                range_from=10, range_to=20, name="Fine Bereich", kind="rotate"))
            session.add(profile)
            session.commit()
            self.fixture_id = profile.id

        self.engine_patch = mock.patch.object(editor_module, "engine", lambda: self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.message_patch = mock.patch.object(editor_module.QMessageBox, "information")
        self.message_patch.start()
        self.addCleanup(self.message_patch.stop)

    def test_open_edit_save_preserves_noneditable_profile_metadata(self):
        dialog = editor_module.FixtureEditorDialog(fixture_id=self.fixture_id)
        dialog.show()
        _app.processEvents()
        try:
            dialog._edit_name.setText("Roundtrip Fixture Edited")
            dialog._save()
        finally:
            dialog.deleteLater()
            _app.processEvents()

        with Session(self.engine) as session:
            profile = _load(session, self.fixture_id)
            self.assertEqual(profile.name, "Roundtrip Fixture Edited")
            self.assertEqual(profile.notes, "Wichtige Notiz")
            mode = profile.modes[0]
            self.assertEqual(mode.description, "Modus-Beschreibung")
            channel = mode.channels[0]
            self.assertTrue(channel.invert)
            self.assertEqual(channel.resolution, "16bit")
            self.assertEqual(
                [(r.range_from, r.range_to, r.name, r.kind) for r in channel.ranges],
                [(10, 20, "Fine Bereich", "rotate")],
            )


if __name__ == "__main__":
    unittest.main()
