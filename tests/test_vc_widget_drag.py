"""VC-WIDGET-DRAG (Guard): platzierte VC-Widgets lassen sich im Bearbeiten-Modus
per Drag verschieben.

Hintergrund: David beobachtete live (Session 2026-07-07), dass sich Button/Fader/
SpeedDial im VC-Bearbeiten-Modus nicht ziehen ließen. Headless liess sich das
NICHT reproduzieren — der Drag-Pfad (VCWidget.mousePressEvent -> _dragging=True,
VCWidget.mouseMoveEvent -> self.move) funktioniert für alle drei Typen (sie malen
sich selbst und delegieren im Edit-Modus an super()). Diese Tests nageln das
korrekte Verhalten fest (Regressions-Wächter): bricht ein künftiger Umbau die
Kern-Drag-Interaktion, schlagen sie an. Der ursprünglich gemeldete Live-Effekt
bleibt offen für eine Live-/Computer-Use-Repro (vermutlich szenario-spezifische
Event-Zustellung im echten Fenster).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QPointF, QPoint, QEvent
from PySide6.QtGui import QMouseEvent

from src.ui.virtualconsole.vc_slider import VCSlider
from src.ui.virtualconsole.vc_button import VCButton
from src.ui.virtualconsole.vc_speedial import VCSpeedDial
from src.ui.virtualconsole.vc_frame import VCFrame

_app = QApplication.instance() or QApplication([])


def _press(w, x, y):
    e = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y),
                    QPointF(w.mapToGlobal(QPoint(int(x), int(y)))),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier)
    w.mousePressEvent(e)


def _move(w, x, y):
    e = QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y),
                    QPointF(w.mapToGlobal(QPoint(int(x), int(y)))),
                    Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier)
    w.mouseMoveEvent(e)


def _drag_moves(w, cx, cy, dx, dy):
    """Drückt im Body-Zentrum (cx,cy) und zieht um (dx,dy); liefert (start, end)."""
    start = (w.geometry().x(), w.geometry().y())
    _press(w, cx, cy)
    _move(w, cx + dx, cy + dy)
    end = (w.geometry().x(), w.geometry().y())
    return start, end


class VCWidgetDragTest(unittest.TestCase):
    def setUp(self):
        self.parent = QWidget()
        self.parent.resize(1000, 800)

    def _mk(self, cls):
        w = cls("W", self.parent)
        w.setGeometry(200, 200, 120, 120)   # groß genug, Zentrum weit weg von Resize-Zonen
        w.show()
        w.set_edit_mode(True)
        return w

    def test_slider_drags(self):
        w = self._mk(VCSlider)
        start, end = _drag_moves(w, 60, 60, 40, 50)
        self.assertTrue(w._dragging or end != start, "Fader startet keinen Drag")
        self.assertEqual(end, (start[0] + 40, start[1] + 50))

    def test_button_drags(self):
        w = self._mk(VCButton)
        start, end = _drag_moves(w, 60, 60, 40, 50)
        self.assertEqual(end, (start[0] + 40, start[1] + 50), "Button bewegt sich nicht")

    def test_speeddial_drags(self):
        w = self._mk(VCSpeedDial)
        start, end = _drag_moves(w, 60, 60, 40, 50)
        self.assertEqual(end, (start[0] + 40, start[1] + 50), "SpeedDial bewegt sich nicht")

    def test_button_in_frame_drags(self):
        # Verschachtelt: Button als Kind eines VCFrame — der zuletzt plausible
        # Kandidat für den Live-Effekt. Draggt der Frame-Kind-Button?
        frame = VCFrame("F", self.parent)
        frame.setGeometry(100, 100, 500, 500)
        frame.show()
        btn = VCButton("B")
        frame.add_child_to_page(btn, page=0)
        btn.setGeometry(50, 50, 120, 120)
        btn.show()
        frame.set_edit_mode(True)          # rekursiv auch aufs Kind
        start, end = _drag_moves(btn, 60, 60, 40, 50)
        self.assertEqual(end, (start[0] + 40, start[1] + 50),
                         "Button im Frame bewegt sich nicht (echter VC-WIDGET-DRAG-Bug?)")


if __name__ == "__main__":
    unittest.main()
