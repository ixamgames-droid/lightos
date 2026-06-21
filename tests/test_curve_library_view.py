"""B2 / FW-4(a): Standalone-Kurven-Bibliothek-View — CRUD gegen die
get_curve_library()-Singleton (In-Memory, DB-frei). Presets bleiben gesperrt."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.engine.curve_library as cl
from src.ui.views.curve_library_view import CurveLibraryView

_app = QApplication.instance() or QApplication([])


def _new_curve(name, mode="smooth"):
    c = cl.get_curve_library().presets()[0].copy()
    c.name = name
    c.mode = mode
    return c


class CurveLibraryViewTest(unittest.TestCase):
    def setUp(self):
        cl._library = None          # frische Bibliothek (nur Presets, keine User-Kurven)

    def tearDown(self):
        cl._library = None

    def test_lists_all_curves(self):
        v = CurveLibraryView()
        self.assertEqual(v._list.count(), len(cl.get_curve_library().all()))
        self.assertGreaterEqual(len(cl.get_curve_library().presets()), 1)

    def test_add_user_curve(self):
        v = CurveLibraryView()
        v._do_add(_new_curve("MyCurve"))
        self.assertIn("MyCurve", [c.name for c in cl.get_curve_library().user_curves()])

    def test_duplicate_makes_unique_name(self):
        v = CurveLibraryView()
        c = v._do_add(_new_curve("Dup"))
        v._do_duplicate(c)
        names = [c.name for c in cl.get_curve_library().user_curves()]
        self.assertIn("Dup", names)
        self.assertTrue(any(n.startswith("Dup Kopie") for n in names))

    def test_rename_user_curve(self):
        v = CurveLibraryView()
        c = v._do_add(_new_curve("Old"))
        v._do_rename(c, "New")
        names = [c.name for c in cl.get_curve_library().user_curves()]
        self.assertIn("New", names)
        self.assertNotIn("Old", names)

    def test_delete_user_curve(self):
        v = CurveLibraryView()
        v._do_add(_new_curve("Temp"))
        self.assertTrue(v._do_delete("Temp"))
        self.assertNotIn("Temp", [c.name for c in cl.get_curve_library().user_curves()])

    def test_preset_locked(self):
        v = CurveLibraryView()
        preset = cl.get_curve_library().presets()[0].name
        self.assertFalse(v._do_delete(preset))      # remove() lehnt Presets ab
        v._select(preset)
        v._on_selection()
        self.assertFalse(v._btn_del.isEnabled())     # Löschen für Preset deaktiviert
        self.assertFalse(v._btn_ren.isEnabled())


if __name__ == "__main__":
    unittest.main()
