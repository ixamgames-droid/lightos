"""VC-3D-Optik: Contract des geteilten Paint-Helfers + sichtbares Press-Feedback.

Sichert zu, dass ``paint_button_surface`` (a) ein Face-Rechteck INNERHALB des
Widgets liefert, (b) den gedrueckten Zustand nach unten versetzt (haptisches
Einsinken), (c) bei winzigen Groessen nicht crasht/negativ wird, und dass ein
echter VCButton im gedrueckten vs. normalen Zustand SICHTBAR anders aussieht
(sonst waere das Druckfeedback verloren gegangen).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtCore import QRect, QRectF

from src.ui.virtualconsole.vc_style import paint_button_surface, key_rect, DEPTH

_app = QApplication.instance() or QApplication([])


def _paint(rect, base, pressed, lit):
    """Malt einmal in ein Offscreen-Image und liefert (image, face)."""
    img = QImage(rect.width() + rect.x(), rect.height() + rect.y(),
                 QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    face = paint_button_surface(p, QRectF(rect), QColor(base), pressed, lit)
    p.end()
    return img, face


class TestPaintSurfaceContract(unittest.TestCase):
    def test_face_inside_widget(self):
        rect = QRect(0, 0, 100, 70)
        _img, face = _paint(rect, "#1a3a5c", False, False)
        self.assertGreaterEqual(face.left(), rect.left())
        self.assertGreaterEqual(face.top(), rect.top())
        self.assertLessEqual(face.right(), rect.right() + 0.001)
        self.assertLessEqual(face.bottom(), rect.bottom() + 0.001)

    def test_pressed_face_travels_down(self):
        rect = QRect(0, 0, 100, 70)
        raised = key_rect(QRectF(rect), pressed=False)
        pressed = key_rect(QRectF(rect), pressed=True)
        # Gedrueckt sinkt die Taste um DEPTH nach unten ein.
        self.assertAlmostEqual(pressed.top() - raised.top(), DEPTH, places=3)

    def test_tiny_size_does_not_crash_or_go_negative(self):
        for w, h in [(1, 1), (6, 6), (16, 12), (40, 40)]:
            rect = QRect(0, 0, w, h)
            _img, face = _paint(rect, "#2e5c3a", True, True)
            self.assertGreaterEqual(face.height(), 1.0)
            self.assertGreaterEqual(face.width(), 0.0)

    def test_returns_qrectf(self):
        _img, face = _paint(QRect(0, 0, 80, 50), "#5c2e2e", False, True)
        self.assertIsInstance(face, QRectF)


class TestPressFeedbackVisible(unittest.TestCase):
    def test_button_pressed_looks_different(self):
        from src.ui.virtualconsole.vc_button import VCButton
        b = VCButton("GO")
        b.resize(96, 72)
        b._pressed = False
        normal = b.grab().toImage()
        b._pressed = True
        pressed = b.grab().toImage()
        # Die Bilder muessen sich unterscheiden — sonst kein sichtbares Feedback.
        self.assertNotEqual(normal, pressed)

    def test_active_snap_looks_different_from_idle(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        b = VCButton("SNAP")
        b.action = ButtonAction.LIBRARY_SNAP
        b.resize(96, 72)
        b._snap_active = False
        idle = b.grab().toImage()
        b._snap_active = True
        active = b.grab().toImage()
        self.assertNotEqual(idle, active)


if __name__ == "__main__":
    unittest.main()
