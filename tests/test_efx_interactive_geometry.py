"""EFX-Editor: interaktive Geometrie (Zentrum/Größe per Drag) + Großansicht-Popout.

Sichert ab, dass die interaktive Vorschau und das Popout-Fenster die Geometrie
(„Gobo"/Figur) ins Modell schreiben und die Editor-Spinboxen synchron halten.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from src.ui.views.efx_view import EfxView, EfxPreviewWidget, EfxPopoutDialog
from src.core.engine.efx import EfxInstance


class PreviewGeometryTest(unittest.TestCase):
    def test_from_px_mapping(self):
        pw = EfxPreviewWidget(editable=True)
        pw.resize(300, 300)
        m, w, h = pw._metrics()
        # Feldmitte → Pan/Tilt ~128
        pan, tilt = pw._from_px(m + w / 2, m + h / 2)
        self.assertAlmostEqual(pan, 127.5, delta=2)
        self.assertAlmostEqual(tilt, 127.5, delta=2)
        # oben links → 0/0, geklemmt
        pan, tilt = pw._from_px(-50, -50)
        self.assertEqual((pan, tilt), (0.0, 0.0))

    def test_emit_geom_updates_model_and_callback(self):
        pw = EfxPreviewWidget(editable=True)
        e = EfxInstance("t")
        pw.set_efx(e)
        seen = {}
        pw.set_geometry_callback(lambda upd: seen.update(upd))
        pw._emit_geom({"x_offset": 200, "y_offset": 40})
        self.assertEqual(e.x_offset, 200.0)
        self.assertEqual(e.y_offset, 40.0)
        self.assertEqual(seen, {"x_offset": 200, "y_offset": 40})


class ViewGeometrySyncTest(unittest.TestCase):
    def setUp(self):
        self.v = EfxView()
        self.v._add_efx()
        self.cur = self.v._current
        self.assertIsNotNone(self.cur)

    def test_apply_geometry_syncs_spins(self):
        self.v._apply_geometry({"x_offset": 210, "y_offset": 33,
                                "width": 64, "height": 48, "rotation": 90})
        self.assertEqual(self.cur.x_offset, 210.0)
        self.assertEqual(self.cur.width, 64.0)
        self.assertEqual(self.v._xoff_spin.value(), 210.0)
        self.assertEqual(self.v._yoff_spin.value(), 33.0)
        self.assertEqual(self.v._width_spin.value(), 64.0)
        self.assertEqual(self.v._rot_spin.value(), 90.0)

    def test_popout_bidirectional_sync(self):
        self.v._open_popout()
        self.assertIsNotNone(self.v._popout)
        # Popout-Spin → Modell + Editor-Spin
        self.v._popout._spins["x_offset"].setValue(177)
        self.assertEqual(self.cur.x_offset, 177.0)
        self.assertEqual(self.v._xoff_spin.value(), 177.0)
        # Editor-seitige Geometrie-Änderung → Popout-Spin folgt
        self.v._apply_geometry({"x_offset": 90})
        self.assertEqual(self.v._popout._spins["x_offset"].value(), 90.0)
        self.v._on_popout_closed()

    def test_inline_preview_is_editable_and_wired(self):
        self.assertTrue(self.v._preview._editable)
        self.assertIsNotNone(self.v._preview._geom_cb)


if __name__ == "__main__":
    unittest.main()
