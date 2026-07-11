"""Fixture-Editor: Channel-Edit/Delete/Move korrumpiert Nachbar-Channels nicht mehr,
und das Ueberschreiben eines Fixtures hinterlaesst keine Waisen-Channels.

Regression (adversariale UI-Bug-Jagd 2026-07-09):
- _ModeTab.refresh() synchronisierte die (nach del/move) STALE Tabelle per Index in die
  bereits mutierte channels-Liste zurueck -> Name/Default/Highlight des Folge-Channels
  korrumpiert. Fix: _sync_from_table() VOR der Mutation, danach nur _rebuild_rows().
- _save() loeschte alte Modes per Core-Bulk-delete(FixtureMode) — das umgeht die ORM-
  Cascade (FK channels.mode_id ohne ON DELETE CASCADE) -> Waisen-Channels/-Ranges.
  Fix: ORM-Delete (s.delete(mode)) je Mode.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


class ModeTabCorruptionTest(unittest.TestCase):
    def _tab_with_channels(self):
        from src.ui.widgets.fixture_editor import _ModeTab
        tab = _ModeTab("M")
        tab.load_mode_data("M", [
            {"name": "A", "attribute": "raw", "default": 10, "highlight": 210},
            {"name": "B", "attribute": "raw", "default": 20, "highlight": 220},
            {"name": "C", "attribute": "raw", "default": 30, "highlight": 230},
        ])
        return tab

    def test_delete_row_keeps_remaining_channels_intact(self):
        tab = self._tab_with_channels()
        try:
            # Ungespeicherte Live-Edit in Zeile 1 (Name B -> B2)
            tab._tbl.item(1, 1).setText("B2")
            tab._tbl.selectRow(0)          # Channel A zum Loeschen waehlen
            tab._del_channel()
            names = [c["name"] for c in tab.channels]
            defaults = [c["default"] for c in tab.channels]
            self.assertEqual(names, ["B2", "C"])       # frueher korrupt: ["A","B2"]
            self.assertEqual(defaults, [20, 30])       # Default zieht mit dem Channel mit
        finally:
            tab.deleteLater(); _app.processEvents()

    def test_move_down_swaps_whole_channel_not_just_attribute(self):
        tab = self._tab_with_channels()
        try:
            tab._tbl.selectRow(0)
            tab._move(1)                    # A nach unten (A<->B)
            names = [c["name"] for c in tab.channels]
            defaults = [c["default"] for c in tab.channels]
            self.assertEqual(names, ["B", "A", "C"])
            self.assertEqual(defaults, [20, 10, 30])   # Name UND Default getauscht
        finally:
            tab.deleteLater(); _app.processEvents()

    def test_load_mode_data_does_not_corrupt_on_switch(self):
        tab = self._tab_with_channels()
        try:
            # Simulierter Edit im alten Mode, dann Wechsel auf einen kuerzeren Mode
            tab._tbl.item(0, 1).setText("EDIT")
            tab.load_mode_data("M2", [{"name": "X", "attribute": "raw",
                                       "default": 5, "highlight": 250}])
            self.assertEqual([c["name"] for c in tab.channels], ["X"])
            self.assertEqual(tab.channels[0]["default"], 5)
        finally:
            tab.deleteLater(); _app.processEvents()


class ModeDeleteCascadeTest(unittest.TestCase):
    """#5: ORM-Delete raeumt Channels ab, Core-Bulk-delete laesst Waisen — in-memory,
    beruehrt die echte Fixture-DB NICHT."""

    def _fresh_engine(self):
        from sqlalchemy import create_engine
        from src.core.database.models import Base
        eng = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(eng)
        return eng

    def _seed_mode(self, s):
        from src.core.database.models import FixtureMode, FixtureChannel
        mode = FixtureMode(fixture_id=1, name="M", channel_count=2)
        s.add(mode); s.flush()
        s.add(FixtureChannel(mode_id=mode.id, channel_number=1, name="c1"))
        s.add(FixtureChannel(mode_id=mode.id, channel_number=2, name="c2"))
        s.flush()
        return mode

    def test_orm_delete_cascades_to_channels(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.database.models import FixtureMode, FixtureChannel
        with Session(self._fresh_engine()) as s:
            self._seed_mode(s)
            self.assertEqual(len(s.execute(select(FixtureChannel)).scalars().all()), 2)
            for m in s.execute(select(FixtureMode)).scalars().all():
                s.delete(m)                 # wie im Fix
            s.flush()
            self.assertEqual(len(s.execute(select(FixtureChannel)).scalars().all()), 0)

    def test_core_bulk_delete_would_leave_orphans(self):
        """Belegt, warum der Fix noetig ist: das alte Bulk-delete laesst Waisen."""
        from sqlalchemy import select, delete
        from sqlalchemy.orm import Session
        from src.core.database.models import FixtureMode, FixtureChannel
        with Session(self._fresh_engine()) as s:
            self._seed_mode(s)
            s.execute(delete(FixtureMode))   # altes Verhalten (Core-Bulk)
            s.flush()
            self.assertEqual(len(s.execute(select(FixtureChannel)).scalars().all()), 2)


if __name__ == "__main__":
    unittest.main()
