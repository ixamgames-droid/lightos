"""STAB-29: nach „Neue Show" oder „Show oeffnen" gibt es nichts rueckgaengig zu machen.

Gefunden in der Review zu FM-38 (29.09.2026): der Rueckgaengig-Verlauf
ueberlebte den Showwechsel. Seine Eintraege zielen auf Geraete-NUMMERN — Strg+Z
nach dem Oeffnen einer anderen Show loeschte ein Geraet der NEUEN Show, das
zufaellig dieselbe Nummer traegt. Echter Weg: AppState, Undo-Stapel, save/load.
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state                         # noqa: E402
from src.core.database.models import PatchedFixture              # noqa: E402
from src.core.show.show_file import load_show, reset_show, save_show  # noqa: E402
from src.core.undo import get_undo_stack                         # noqa: E402


def _geraet(fid, label, adr):
    return PatchedFixture(fid=fid, label=label, fixture_profile_id=1, mode_name="m",
                          universe=1, address=adr, channel_count=8, fixture_type="par")


class ShowwechselTest(unittest.TestCase):

    def setUp(self):
        reset_show()
        self.st = get_state()
        self.stack = get_undo_stack()
        self.addCleanup(self.stack.clear)
        d = tempfile.mkdtemp()
        self.andere = os.path.join(d, "andere.lshow")
        # die ANDERE Show: Geraet 1 heisst „Fremd"
        self.st.add_fixture(_geraet(1, "Fremd", 1), undoable=False)
        save_show(self.andere)
        reset_show()

    def test_oeffnen_leert_den_verlauf(self):
        self.st.add_fixture(_geraet(1, "Mein PAR", 1), undoable=True)
        self.assertTrue(self.stack.can_undo(), "Vorbedingung")
        load_show(self.andere)
        self.assertFalse(self.stack.can_undo())
        self.stack.undo()                       # darf nichts tun
        self.assertEqual(["Fremd"], [f.label for f in self.st.get_patched_fixtures()])

    def test_neue_show_leert_den_verlauf(self):
        self.st.add_fixture(_geraet(1, "Mein PAR", 1), undoable=True)
        reset_show()
        self.assertFalse(self.stack.can_undo())
        self.assertFalse(self.stack.can_redo())

    def test_innerhalb_einer_show_bleibt_undo(self):
        """Positivkontrolle: ohne Showwechsel geht Rueckgaengig wie immer."""
        self.st.add_fixture(_geraet(1, "Mein PAR", 1), undoable=True)
        self.stack.undo()
        self.assertEqual([], self.st.get_patched_fixtures())


if __name__ == "__main__":
    unittest.main()
