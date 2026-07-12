"""BH-COLORWHEEL: die angeklickte Farbe muss die unter dem Cursor gemalte sein.

Der Hue-Konusgradient malt bei Schirm-Winkel ``theta`` (CCW von Ost, y-oben) die
Farbe ``(90 - theta) % 360`` — offscreen an der echten QConicalGradient-Ausgabe
gemessen, unabhaengig von Qts CCW-Konvention. Frueher setzte ``_set_from_pos``
aber ``_hue = theta`` (gewaehlte Farbe != angeklickte) und der Marker sass bei
``theta`` statt auf seiner eigenen Farbe. Beide Stellen sind jetzt spiegelbildlich
zur Gradient-Konstruktion. Getestet gegen das TATSAECHLICH gerenderte Widget
(grab()), damit ein Revert einer der beiden Stellen auffliegt.
"""
import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from src.ui.widgets.color_picker import ColorWheel

_app = QApplication.instance() or QApplication([])

SIDE = 201


def _wheel():
    w = ColorWheel()
    w.resize(SIDE, SIDE)
    return w


def _point_at(w, theta_deg, frac=0.6):
    """Schirm-QPoint bei math-Winkel theta (CCW von Ost) im Rad-Bruchteil frac."""
    from PySide6.QtCore import QPoint
    cx, cy = w.width() / 2, w.height() / 2
    radius = (min(w.width(), w.height()) - 8) / 2
    r = radius * frac
    x = cx + math.cos(math.radians(theta_deg)) * r
    y = cy - math.sin(math.radians(theta_deg)) * r
    return QPoint(int(round(x)), int(round(y)))


def _hue_diff(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)


class ClickSelectsPaintedHueTest(unittest.TestCase):
    def test_click_hue_matches_gradient_formula(self):
        """click(theta) -> _hue == (90 - theta) % 360 (gemessene Gradient-Regel)."""
        w = _wheel()
        cx, cy = w.width() / 2, w.height() / 2
        for theta in (0, 30, 60, 90, 150, 210, 270, 330):
            pt = _point_at(w, theta)
            # exakter Winkel des GERUNDETEN Pixels (sonst Pixel-Rundungs-Slop)
            actual = math.degrees(math.atan2(cy - pt.y(), pt.x() - cx)) % 360
            w._set_from_pos(pt)
            self.assertAlmostEqual(w._hue, (90 - actual) % 360, delta=0.5,
                                   msg=f"theta={theta}")

    def test_click_selects_color_under_cursor_end_to_end(self):
        """Gegen die ECHTE Widget-Ausgabe: die per Klick gewaehlte Hue stimmt mit
        der an der Klickstelle GEMALTEN Hue ueberein (fails auf altem Klick-Code)."""
        w = _wheel()
        w.set_hsv(0.0, 1.0, 1.0)                 # Marker bei Hue 0 -> weg von Sued/Ost
        img = w.grab().toImage()
        for theta in (0, 300, 240, 180):         # Klickstellen abseits des Markers
            pt = _point_at(w, theta, frac=0.82)  # nahe Rand: Weiss-Overlay ~transparent
            painted = QColor(img.pixel(pt.x(), pt.y()))
            ph, ps, pv, _ = painted.getHsv()
            if ps < 40:                          # zu entsaettigt (Overlay/Marker) -> skip
                continue
            w._set_from_pos(pt)
            self.assertLessEqual(_hue_diff(w._hue, ph), 18,
                                 msg=f"theta={theta}: gewaehlt {w._hue}, gemalt {ph}")


class MarkerSitsOnOwnColorTest(unittest.TestCase):
    def _marker_centroid(self, img):
        """Schwerpunkt der reinweissen Marker-Pixel (am voll gesaettigten Rand ist
        Reinweiss eindeutig der Marker)."""
        xs, ys, n = 0, 0, 0
        for y in range(img.height()):
            for x in range(img.width()):
                c = QColor(img.pixel(x, y))
                if c.red() > 250 and c.green() > 250 and c.blue() > 250:
                    xs += x
                    ys += y
                    n += 1
        return (xs / n, ys / n) if n else None

    def test_marker_placed_where_its_hue_is_painted(self):
        """Der Marker fuer Hue H sitzt beim Schirm-Winkel (90 - H) — also GENAU
        dort, wo der Gradient Hue H malt (fails auf altem Marker-Code)."""
        w = _wheel()
        for H in (0.0, 90.0, 180.0, 270.0):
            w.set_hsv(H, 1.0, 1.0)               # volle Saettigung -> Marker am Rand
            img = w.grab().toImage()
            c = self._marker_centroid(img)
            self.assertIsNotNone(c, msg=f"Marker fuer H={H} nicht gefunden")
            cx, cy = w.width() / 2, w.height() / 2
            theta_m = math.degrees(math.atan2(cy - c[1], c[0] - cx)) % 360
            self.assertLessEqual(_hue_diff((90 - theta_m) % 360, H), 18,
                                 msg=f"H={H}: Marker bei theta={theta_m:.0f}")


if __name__ == "__main__":
    unittest.main()
