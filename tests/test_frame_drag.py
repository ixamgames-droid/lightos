"""FRM-01: vorhandene VC-Widgets per Drag in einen Frame ziehen (und wieder heraus).

Getestet wird die Reparenting-Logik (Geometrie-Hit-Test) von VCCanvas.handle_drag_drop
inkl. Serialisierung des Kindes unter dem Frame.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint

from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_button import VCButton

_app = QApplication.instance() or QApplication([])


class _CanvasTest(unittest.TestCase):
    """Basis mit sauberem Abbau der erzeugten Canvases (sonst bleiben sie beim
    globalen MIDI-Manager registriert und destabilisieren die Gesamt-Suite)."""

    def setUp(self):
        self._canvases = []

    def tearDown(self):
        for c in self._canvases:
            try:
                c._teardown_midi()
            except Exception:
                pass
            c.setParent(None)
            c.deleteLater()
        self._canvases.clear()
        _app.processEvents()

    def _canvas_with_frame(self):
        canvas = VCCanvas()
        self._canvases.append(canvas)
        canvas.set_edit_mode(True)
        frame = canvas._add_widget("VCFrame", QPoint(200, 60))
        frame.resize(300, 200)          # Geometrie 200..500 / 60..260
        return canvas, frame


class FrameDragTest(_CanvasTest):
    def test_drag_into_frame(self):
        canvas, frame = self._canvas_with_frame()
        btn = canvas._add_widget("VCButton", QPoint(20, 20))
        self.assertIs(btn.parent(), canvas)
        btn.move(300, 120)          # Mittelpunkt ~ (360,150) liegt im Frame
        canvas.handle_drag_drop(btn)
        self.assertIs(btn.parent(), frame)

    def test_drag_out_of_frame(self):
        canvas, frame = self._canvas_with_frame()
        btn = canvas._add_widget("VCButton", QPoint(300, 120))
        canvas.handle_drag_drop(btn)            # zuerst hinein
        self.assertIs(btn.parent(), frame)
        btn.move(350, 10)                       # frame-lokal -> Canvas ~ (550,70), außerhalb
        canvas.handle_drag_drop(btn)
        self.assertIs(btn.parent(), canvas)

    def test_frame_not_nested(self):
        canvas, frame = self._canvas_with_frame()
        f2 = canvas._add_widget("VCFrame", QPoint(220, 80))   # Mitte im ersten Frame
        canvas.handle_drag_drop(f2)             # Frame-in-Frame -> ignoriert
        self.assertIs(f2.parent(), canvas)

    def test_reparented_child_serialized_under_frame(self):
        canvas, frame = self._canvas_with_frame()
        btn = canvas._add_widget("VCButton", QPoint(300, 120))
        btn.caption = "InFrame"
        canvas.handle_drag_drop(btn)
        self.assertIs(btn.parent(), frame)
        direct = canvas.findChildren(
            VCButton, options=Qt.FindChildOption.FindDirectChildrenOnly)
        self.assertNotIn(btn, direct)            # nicht mehr direkt am Canvas
        caps = [c.get("caption") for c in frame.to_dict().get("children", [])]
        self.assertIn("InFrame", caps)           # serialisiert unter dem Frame


class FrameDragHighlightTest(_CanvasTest):
    """FRM-02: ein Widget mit aktivem Effekt-Glow (QGraphicsDropShadowEffect) darf
    beim Reinziehen NICHT verschwinden. Der Glow ueberlebt setParent() sonst mit
    einem veralteten Offscreen-Clip -> das Widget zeichnet nichts mehr."""

    def test_drag_into_frame_with_highlight_stays_visible(self):
        canvas, frame = self._canvas_with_frame()
        btn = canvas._add_widget("VCButton", QPoint(20, 20))
        btn.set_effect_highlight(True)
        eff_before = btn.graphicsEffect()
        self.assertIsNotNone(eff_before)          # Glow aktiv -> Vanish-Trigger
        btn.move(300, 120)                        # Mittelpunkt im Frame
        canvas.handle_drag_drop(btn)
        self.assertIs(btn.parent(), frame)
        self.assertFalse(btn.isHidden())          # nicht „wie geloescht"
        eff_after = btn.graphicsEffect()
        # Glow bleibt sichtbar, aber als FRISCHES Objekt (frischer Clip unterm Frame).
        self.assertIsNotNone(eff_after)
        self.assertIsNot(eff_after, eff_before)

    def test_drag_into_frame_raises_above_existing_child(self):
        canvas, frame = self._canvas_with_frame()
        first = canvas._add_widget("VCButton", QPoint(300, 120))
        canvas.handle_drag_drop(first)            # schon im Frame
        self.assertIs(first.parent(), frame)
        second = canvas._add_widget("VCButton", QPoint(20, 20))
        second.move(310, 130)
        canvas.handle_drag_drop(second)           # neu hinein -> muss zuoberst liegen
        self.assertIs(second.parent(), frame)
        kids = [c for c in frame.children() if isinstance(c, VCButton)]
        self.assertEqual(kids[-1], second)        # raise_(): zuletzt = oberste Lage


if __name__ == "__main__":
    unittest.main()
