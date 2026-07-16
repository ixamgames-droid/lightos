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
from PySide6.QtCore import QRect, QRectF, QPoint

from src.ui.virtualconsole.vc_style import (
    paint_button_surface, key_rect, DEPTH, paint_slider_handle, paint_dial_knob)

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


class TestBadgeTextInset(unittest.TestCase):
    """VC3D-03: die oben-rechts belegte Spalte (Gobo/Farb-Badge) wird aus dem
    Text-Rechteck ausgespart, damit Tastentext nicht darunter laeuft."""

    def test_inset_values(self):
        from src.ui.virtualconsole.vc_button import _badge_text_right_inset
        self.assertEqual(_badge_text_right_inset(False, 0, False), 0)      # nichts -> kein Inset
        self.assertEqual(_badge_text_right_inset(False, 0, True), 16 + 8)  # nur Badge
        self.assertEqual(_badge_text_right_inset(True, 20, False), 20 + 8)  # nur Gobo
        self.assertEqual(_badge_text_right_inset(True, 10, True),          # beide -> Maximum
                         max(10 + 8, 16 + 8))

    def test_inset_floor_keeps_text_on_narrow_button(self):
        # Review-Regression: schmaler Button (36px Face) + breiter Gobo -> Inset
        # auf halbe Face-Breite gedeckelt, sonst verschwindet die Beschriftung.
        from src.ui.virtualconsole.vc_button import _badge_text_right_inset
        self.assertEqual(_badge_text_right_inset(True, 26, False, face_w=36), 18)
        # breiter Button: kein Deckeln, voller Inset
        self.assertEqual(_badge_text_right_inset(True, 26, False, face_w=200), 26 + 8)

    def test_button_with_badge_and_long_caption_renders(self):
        from src.ui.virtualconsole.vc_button import VCButton
        b = VCButton("PAR Farbwechsel Sehr Langer Name")
        b._gobo_icon = lambda: None
        b._color_badge_colors = lambda: [QColor("#ff0000"), QColor("#00ff00")]
        b._badge_index = 0
        b.resize(96, 72)
        img = b.grab().toImage()
        self.assertEqual(img.width(), 96)
        # Farb-Badge (oben rechts) bleibt sichtbar: rote Pixel in der Badge-Zone
        found_red = any(
            QColor(img.pixel(x, y)).red() > 180 and QColor(img.pixel(x, y)).green() < 120
            for x in range(96 - 22, 96 - 2) for y in range(2, 22)
        )
        self.assertTrue(found_red, "Farb-Badge sollte oben rechts sichtbar bleiben")


class TestBevelSaturationIndependent(unittest.TestCase):
    """VC3D-03: auf voll gesaettigten Farben ist QColor.lighter() ein No-Op
    (V bereits 255) — die feste Bevel-Kante macht die Woelbung trotzdem lesbar:
    die obere Glanzkante ist heller (weisslicher) als die Face-Mitte."""

    def _top_vs_mid(self, base, chan_a, chan_b):
        img, face = _paint(QRect(0, 0, 80, 60), base, pressed=False, lit=False)
        cx = int(face.center().x())
        mid = QColor(img.pixel(cx, int(face.center().y())))
        top_bri = max(
            getattr(QColor(img.pixel(cx, int(face.top()) + dy)), chan_a)()
            + getattr(QColor(img.pixel(cx, int(face.top()) + dy)), chan_b)()
            for dy in range(0, 5)
        )
        return top_bri, getattr(mid, chan_a)() + getattr(mid, chan_b)()

    def test_pure_red_top_edge_lighter(self):
        top, mid = self._top_vs_mid("#ff0000", "green", "blue")
        self.assertGreater(top, mid, "obere Bevel-Kante muss auf reinem Rot heller sein")

    def test_pure_blue_top_edge_lighter(self):
        top, mid = self._top_vs_mid("#0000ff", "red", "green")
        self.assertGreater(top, mid, "obere Bevel-Kante muss auf reinem Blau heller sein")


def _img_for(w, h):
    img = QImage(max(1, w), max(1, h), QImage.Format.Format_ARGB32)
    img.fill(QColor("#0d1117"))
    return img


def _lum(img, x, y):
    c = img.pixelColor(int(x), int(y))
    return c.red() + c.green() + c.blue()


class TestSliderHandle3D(unittest.TestCase):
    """VC3D-02: plastischer Fader-Griff (paint_slider_handle)."""

    def test_tiny_sizes_do_not_crash(self):
        for w, h in [(1, 1), (4, 3), (20, 8), (60, 8)]:
            img = _img_for(w + 2, h + 6)
            p = QPainter(img)
            paint_slider_handle(p, QRect(0, 0, w, h), QColor("#aaccff"))
            p.end()   # darf bei keiner Groesse werfen

    def test_handle_top_light_bottom_shadow(self):
        # Woelbung: obere Kante heller als untere (Licht von oben).
        img = _img_for(60, 12)
        p = QPainter(img)
        paint_slider_handle(p, QRect(0, 2, 60, 8), QColor("#8899aa"))
        p.end()
        top = _lum(img, 30, 3)
        bottom = _lum(img, 30, 9)
        self.assertGreater(top, bottom, "Fader-Griff hat keine Licht-oben/Schatten-unten-Woelbung")


class TestDialKnob3D(unittest.TestCase):
    """VC3D-02: plastische Dreh-Knopf-Flaeche (paint_dial_knob)."""

    def test_zero_and_tiny_radius_do_not_crash(self):
        for r in [0, 1, 4, 20]:
            img = _img_for(60, 60)
            p = QPainter(img)
            paint_dial_knob(p, QPoint(30, 30), r, QColor("#2b3244"))
            p.end()

    def test_knob_is_convex_top_brighter_than_bottom(self):
        img = _img_for(60, 60)
        p = QPainter(img)
        paint_dial_knob(p, QPoint(30, 30), 24, QColor("#3a4560"))
        p.end()
        top = _lum(img, 30, 10)     # oben im Knopf (Lichtquelle oben-links + Rand-Glanz)
        bottom = _lum(img, 30, 50)  # unten im Knopf (Schattenkante)
        self.assertGreater(top, bottom, "Dreh-Knopf hat keine Woelbung (oben nicht heller als unten)")


if __name__ == "__main__":
    unittest.main()
