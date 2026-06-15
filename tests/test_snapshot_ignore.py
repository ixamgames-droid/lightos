"""SNP-01: Snapshots — Kanäle nachträglich ignorieren.

Pro Snapshot lassen sich einzelne (fid, attr)-Kanäle vom Anwenden ausschließen;
der gespeicherte Wert bleibt erhalten, wird aber nicht in den Programmer geschrieben.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.ui.views.snapshots_view import Snapshot, SnapshotIgnoreDialog

_app = QApplication.instance() or QApplication([])


class SnapshotModelTest(unittest.TestCase):
    def test_round_trip_ignored(self):
        s = Snapshot("t", {1: {"intensity": 200, "color_r": 50}, 2: {"pan": 128}},
                     ignored={(1, "color_r")})
        s2 = Snapshot.from_dict(s.to_dict())
        self.assertEqual(s2.ignored, {(1, "color_r")})
        self.assertTrue(s2.is_ignored(1, "color_r"))
        self.assertFalse(s2.is_ignored(1, "intensity"))

    def test_backward_compat_no_ignored(self):
        s = Snapshot.from_dict({"name": "x", "values": {"1": {"intensity": 10}}})
        self.assertEqual(s.ignored, set())
        self.assertEqual(s.ignored_count(), 0)


class IgnoreDialogTest(unittest.TestCase):
    def _snap(self):
        return Snapshot("t", {1: {"intensity": 200, "color_r": 50}, 2: {"pan": 128}})

    def test_get_ignored_reflects_checks(self):
        dlg = SnapshotIgnoreDialog(self._snap())
        dlg._list.item(0).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(len(dlg.get_ignored()), 1)

    def test_set_all_and_invert(self):
        dlg = SnapshotIgnoreDialog(self._snap())
        n = dlg._list.count()
        self.assertEqual(n, 3)
        dlg._set_all(True)
        self.assertEqual(len(dlg.get_ignored()), n)
        dlg._invert()
        self.assertEqual(len(dlg.get_ignored()), 0)

    def test_preselects_existing(self):
        snap = Snapshot("t", {1: {"intensity": 200, "color_r": 50}}, ignored={(1, "intensity")})
        dlg = SnapshotIgnoreDialog(snap)
        self.assertEqual(dlg.get_ignored(), {(1, "intensity")})


class ApplyTest(unittest.TestCase):
    def test_apply_skips_ignored(self):
        from src.ui.views.snapshots_view import SnapshotsView
        from src.core.app_state import get_state
        state = get_state()
        state.clear_programmer()
        view = SnapshotsView()
        view._snapshots[0] = Snapshot("t", {1: {"intensity": 200, "color_r": 50}},
                                      ignored={(1, "color_r")})
        view.apply(0)
        self.assertEqual(state.get_programmer_value(1, "intensity"), 200)
        self.assertIsNone(state.get_programmer_value(1, "color_r"))   # ignoriert
        state.clear_programmer()


if __name__ == "__main__":
    unittest.main()
