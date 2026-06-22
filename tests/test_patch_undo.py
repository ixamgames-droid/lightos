"""Globaler Command-Undo im Patch (UI-02 Verify-Runde).

Deckt die bisher ungetestete Luecke ab: Fixture loeschen im Patch ist
rueckgaengig-machbar ueber den GLOBALEN UndoStack (Haupt-Ctrl+Z), getrennt vom
VC-Canvas-Undo. `patch_view._delete_selected` ruft `remove_fixture(fid)` mit dem
Default `undoable=True` — genau dieser Pfad wird hier verifiziert:
loeschen -> undo() stellt das Fixture (inkl. Adresse/Universe) wieder her ->
redo() loescht es erneut.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.engine.function_manager import get_function_manager
from src.core.show.show_file import reset_show
from src.core.undo import get_undo_stack


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _any_pid() -> int:
    """Irgendein gueltiges Builtin-Profil — der Undo-Test ist profil-agnostisch."""
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id)).scalars().first())


class PatchUndoTest(unittest.TestCase):

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.undo = get_undo_stack()
        self.undo.clear()  # Singleton ueber Prozess -> pro Test sauber starten

    def tearDown(self):
        self.fm.stop_all()
        self.undo.clear()

    def _fids(self):
        return {f.fid for f in self.state.get_patched_fixtures()}

    def _add(self, fid, addr=1):
        # undoable=False: das Setup-Patchen soll NICHT auf dem Undo-Stack landen.
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=f"Fix {fid}", fixture_profile_id=_any_pid(),
            mode_name="", universe=1, address=addr, channel_count=1,
            manufacturer_name="Test", fixture_name="Test", fixture_type="dimmer"),
            undoable=False)

    def test_setup_add_not_on_stack(self):
        """undoable=False darf den Stack nicht fuellen (Vorbedingung)."""
        self._add(3)
        self.assertFalse(self.undo.can_undo())

    def test_delete_fixture_is_undoable(self):
        self._add(1)
        self.assertIn(1, self._fids())

        # Loeschen wie patch_view._delete_selected (Default undoable=True)
        self.state.remove_fixture(1)
        self.assertNotIn(1, self._fids())
        self.assertTrue(self.undo.can_undo(), "Loeschen muss ein Undo-Command pushen")

        # Ctrl+Z: Fixture kommt zurueck
        self.undo.undo()
        self.assertIn(1, self._fids(),
                      "Undo muss das geloeschte Fixture wiederherstellen")

        # Ctrl+Y: erneut geloescht
        self.assertTrue(self.undo.can_redo())
        self.undo.redo()
        self.assertNotIn(1, self._fids(), "Redo muss das Fixture wieder loeschen")

    def test_restored_fixture_keeps_address(self):
        self._add(7, addr=42)
        before = next(f for f in self.state.get_patched_fixtures() if f.fid == 7)
        addr, uni = before.address, before.universe

        self.state.remove_fixture(7)
        self.undo.undo()

        after = next(f for f in self.state.get_patched_fixtures() if f.fid == 7)
        self.assertEqual((after.address, after.universe), (addr, uni),
                         "Wiederhergestelltes Fixture muss Adresse/Universe behalten")

    def test_undo_does_not_repush(self):
        """undo()/redo() duerfen sich nicht selbst auf den Stack legen
        (Re-Push-Schutz): nach genau einem Loeschen gibt es genau ein Undo."""
        self._add(5)
        self.state.remove_fixture(5)
        self.undo.undo()
        # Nach dem Undo darf KEIN weiteres Undo moeglich sein.
        self.assertFalse(self.undo.can_undo(),
                         "undo() darf die Gegenoperation nicht erneut pushen")


if __name__ == "__main__":
    unittest.main()
