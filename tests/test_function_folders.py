"""FLD-01a: Der Funktions-Manager zeigt die verschachtelte folder-Hierarchie."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.ui.views.function_manager_view import FunctionManagerView

_app = QApplication.instance() or QApplication([])


def _find_item(tree, fid):
    def walk(it):
        if it.data(0, Qt.ItemDataRole.UserRole) == fid:
            return it
        for i in range(it.childCount()):
            r = walk(it.child(i))
            if r:
                return r
        return None
    root = tree.invisibleRootItem()
    for i in range(root.childCount()):
        r = walk(root.child(i))
        if r:
            return r
    return None


class FunctionFolderTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m1 = RgbMatrixInstance(name="Tief Blau", cols=2, rows=1,
                                    algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2])
        self.m1.folder = "Blau/Sommer"
        self.fm.add(self.m1)
        self.m2 = RgbMatrixInstance(name="Ohne Ordner", cols=2, rows=1,
                                    algorithm=RgbAlgorithm.CHASE, fixture_grid=[3, 4])
        self.m2.folder = ""
        self.fm.add(self.m2)

    def tearDown(self):
        self.fm.remove(self.m1.id)
        self.fm.remove(self.m2.id)

    def test_nested_folders_built(self):
        view = FunctionManagerView()
        view._refresh_tree()
        item = _find_item(view._tree, self.m1.id)
        self.assertIsNotNone(item)
        sommer = item.parent()
        self.assertEqual(sommer.text(0), "Sommer")
        self.assertIsNone(sommer.data(0, Qt.ItemDataRole.UserRole))   # Ordner
        blau = sommer.parent()
        self.assertEqual(blau.text(0), "Blau")
        self.assertIsNone(blau.data(0, Qt.ItemDataRole.UserRole))

    def test_no_folder_stays_under_type(self):
        view = FunctionManagerView()
        view._refresh_tree()
        item = _find_item(view._tree, self.m2.id)
        self.assertIsNotNone(item)
        # Direkt unter der Typ-Gruppe (kein Ordner dazwischen): Parent hat keinen Parent
        # ausser dem unsichtbaren Root.
        parent = item.parent()
        self.assertIsNotNone(parent)
        self.assertIsNone(parent.data(0, Qt.ItemDataRole.UserRole))   # Typ-Gruppe
        grandparent = parent.parent()
        self.assertIsNone(grandparent)        # Typ-Gruppe liegt direkt unter Root


if __name__ == "__main__":
    unittest.main()
