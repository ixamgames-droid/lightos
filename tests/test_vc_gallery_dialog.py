"""VC-IMG Galerie (PR B): grafischer Auswaehler-Dialog. Headless — kein exec()."""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.show import vc_assets, vc_gallery
from src.ui.virtualconsole.vc_gallery_dialog import VCGalleryDialog

_app = QApplication.instance() or QApplication([])


class TestGalleryDialog(unittest.TestCase):
    def setUp(self):
        vc_assets.set_cache_dir_for_test(tempfile.mkdtemp(prefix="vcgald_"))

    def tearDown(self):
        vc_assets.set_cache_dir_for_test(None)

    def test_constructs_and_populates(self):
        dlg = VCGalleryDialog()          # darf nicht werfen
        self.assertGreaterEqual(len(vc_gallery.entries()), 10)
        dlg.deleteLater()

    def test_choose_gallery_sets_valid_key(self):
        dlg = VCGalleryDialog()
        dlg._choose_gallery("pulse")     # ruft accept(), kein exec noetig
        self.assertTrue(vc_assets.is_valid_key(dlg.selected_key))
        self.assertTrue(os.path.isfile(vc_assets.resolve(dlg.selected_key)))
        dlg.deleteLater()

    def test_choose_unknown_keeps_none(self):
        dlg = VCGalleryDialog()
        dlg._choose_gallery("gibtsnicht")
        self.assertIsNone(dlg.selected_key)
        dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
