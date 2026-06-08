"""Qt-Offscreen-Tests: Bibliothek-Snap (Farbe/Look) auf VC-Tasten legen.

Deckt das „VC-Patching" ab: ein Snap aus der Show-Bibliothek
(src.core.engine.snap_library) wird per Drag/Assign auf einen VCButton gelegt
(ButtonAction.LIBRARY_SNAP) und beim Druck in den Programmer geschrieben.
Tastenverhalten: set (bleibt), flash (nur gehalten), toggle (an/aus, mit
Ruecknahme der vorher aktiven Werte).

Alle Tests laufen mit QT_QPA_PLATFORM=offscreen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QAbstractItemView

from src.core.app_state import get_state
from src.core.engine.snap_library import get_snap_library


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class VcLibrarySnapTest(unittest.TestCase):

    def setUp(self):
        _app()
        self.state = get_state()
        self.state.clear_programmer()
        # Test-Snap: nur Fixture 1 (rot). color_g/color_b dienen dem Restore-Test.
        self.lib = get_snap_library()
        snap = self.lib.add_snap("TEST_rot", "", {1: {"color_r": 255, "color_g": 0}})
        self.sid = snap.id

    def tearDown(self):
        self.state.clear_programmer()
        try:
            self.lib.remove_snap(self.sid)
        except Exception:
            pass

    # ── Drop / Assign ─────────────────────────────────────────────────────────

    def test_snap_to_empty_canvas_creates_button(self):
        """Snap auf leeres Canvas → neuer VCButton mit LIBRARY_SNAP + snap_id."""
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction

        canvas = VCCanvas()
        canvas.set_edit_mode(True)
        canvas.apply_drop(snap_id=self.sid, pos=QPoint(40, 40))

        buttons = canvas.findChildren(VCButton)
        self.assertEqual(len(buttons), 1)
        btn = buttons[0]
        self.assertEqual(btn.action, ButtonAction.LIBRARY_SNAP)
        self.assertEqual(btn.snap_id, self.sid)
        self.assertEqual(btn.caption, "TEST_rot")
        # Standard-Tastenmodus ist „Umschalten".
        self.assertEqual(btn.snap_mode, "toggle")

    def test_snap_to_existing_button(self):
        """Snap auf vorhandenen VCButton → action=LIBRARY_SNAP, snap_id gesetzt."""
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction

        canvas = VCCanvas()
        canvas.set_edit_mode(True)
        btn = VCButton(parent=canvas)
        canvas.apply_drop(snap_id=self.sid, target=btn)

        self.assertEqual(btn.action, ButtonAction.LIBRARY_SNAP)
        self.assertEqual(btn.snap_id, self.sid)

    # ── Tastenverhalten ───────────────────────────────────────────────────────

    def _make_button(self, mode):
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_button import VCButton
        canvas = VCCanvas()
        canvas.set_edit_mode(True)
        btn = VCButton(parent=canvas)
        canvas._assign_snap_to_button(btn, self.sid)
        btn.snap_mode = mode
        return btn

    def test_set_mode_latches(self):
        """set: Druck setzt die Farbe, Loslassen aendert nichts."""
        btn = self._make_button("set")
        btn._trigger(True)
        self.assertEqual(self.state.get_programmer_value(1, "color_r"), 255)
        btn._trigger(False)
        self.assertEqual(self.state.get_programmer_value(1, "color_r"), 255)

    def test_flash_mode_restores_on_release(self):
        """flash: gedrueckt = Farbe, losgelassen = vorheriger Zustand."""
        self.state.set_programmer_value(1, "color_r", 50)
        btn = self._make_button("flash")
        btn._trigger(True)
        self.assertEqual(self.state.get_programmer_value(1, "color_r"), 255)
        btn._trigger(False)
        self.assertEqual(self.state.get_programmer_value(1, "color_r"), 50)

    def test_toggle_mode_on_off(self):
        """toggle: 1. Druck an (Farbe), 2. Druck aus (vorheriger Zustand)."""
        self.state.set_programmer_value(1, "color_r", 50)  # vorbestehend
        btn = self._make_button("toggle")
        # an
        btn._trigger(True)
        self.assertEqual(self.state.get_programmer_value(1, "color_r"), 255)
        self.assertEqual(self.state.get_programmer_value(1, "color_g"), 0)
        self.assertTrue(btn._snap_active)
        # aus → color_r auf 50 zurueck, color_g (vorher None) entfernt
        btn._trigger(True)
        self.assertEqual(self.state.get_programmer_value(1, "color_r"), 50)
        self.assertIsNone(self.state.get_programmer_value(1, "color_g"))
        self.assertFalse(btn._snap_active)

    # ── Serialisierung ────────────────────────────────────────────────────────

    def test_roundtrip_serialization(self):
        """snap_id + snap_mode ueberleben to_dict/apply_dict."""
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        btn = self._make_button("flash")
        d = btn.to_dict()
        btn2 = VCButton()
        btn2.apply_dict(d)
        self.assertEqual(btn2.action, ButtonAction.LIBRARY_SNAP)
        self.assertEqual(btn2.snap_id, self.sid)
        self.assertEqual(btn2.snap_mode, "flash")

    # ── Bibliothek-Panel im VC-Modus ──────────────────────────────────────────

    def test_snap_file_panel_drag_mode(self):
        """SnapFilePanel(drag_to_canvas=True): Baum ist Drag-Only (Export auf Canvas)."""
        from src.ui.views.snap_file_panel import SnapFilePanel
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        canvas = VCCanvas()
        panel = SnapFilePanel(drag_to_canvas=True, canvas=canvas)
        self.assertTrue(panel._drag_to_canvas)
        self.assertIs(panel._canvas, canvas)
        self.assertEqual(panel._tree.dragDropMode(),
                         QAbstractItemView.DragDropMode.DragOnly)


if __name__ == "__main__":
    unittest.main()
