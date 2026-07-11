"""Bug-Hunt-Harvest 8 (BH-CGRENDER, BH-NEXTCUE, BH-CURVEDRAG), 2026-07-12.

- Channel-Group-Slider schreibt ueber die Simple-Desk-Override-Schicht (oberste
  Schicht im Renderer) statt roh ins Live-Universe (wo der 44-Hz-Renderer den Wert
  sofort ueberschrieb -> Slider wirkungslos).
- Playback "Naechste"-Vorschau nutzt CueStack.peek_next() (loop/bounce-korrekt)
  statt naivem idx+1.
- Curve-Editor: Rechtsklick-Loeschen invalidiert einen laufenden Drag (_drag_idx),
  sonst korrumpierte der naechste mouseMove einen anderen Punkt.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.cue_stack import CueStack
from src.core.engine.cue import Cue


def _stack(mode="single", n=3, current=None):
    st = CueStack("T")
    for i in range(n):
        st.cues.append(Cue(number=float(i + 1), label=f"C{i+1}", values={}))
    st.mode = mode
    if current is not None:
        st._current_idx = current
    return st


class PeekNextPublicTest(unittest.TestCase):
    def test_loop_wraps_to_first(self):
        st = _stack(mode="loop", current=2)      # letzte Cue aktiv
        nxt, d = st.peek_next()
        self.assertEqual(nxt, 0, "loop muss auf Cue 1 zurueckspringen (nicht 'Ende')")

    def test_single_at_end_returns_none(self):
        st = _stack(mode="single", current=2)
        nxt, _ = st.peek_next()
        self.assertIsNone(nxt)

    def test_bounce_reverses_at_end(self):
        st = _stack(mode="bounce", current=2)
        nxt, d = st.peek_next()
        self.assertEqual(nxt, 1, "bounce muss am Ende rueckwaerts gehen")
        self.assertEqual(d, -1)


class ChannelGroupOverrideTest(unittest.TestCase):
    def test_apply_value_writes_via_override_layer(self):
        from src.ui.views.channel_groups_view import ChannelGroupsView, ChannelGroup
        writes = []
        fake = SimpleNamespace(
            _groups=[ChannelGroup(name="G", universe=2, channels=[1, 5, 600])],
            _state=SimpleNamespace(
                set_simple_desk_channel=lambda u, c, v: writes.append((u, c, v))),
        )
        fake._groups[0].value = 200
        ChannelGroupsView._apply_value(fake, 0)
        self.assertEqual(writes, [(2, 1, 200), (2, 5, 200)],
                         "muss ueber set_simple_desk_channel gehen (600 gefiltert)")

    def test_apply_value_out_of_range_row_is_noop(self):
        from src.ui.views.channel_groups_view import ChannelGroupsView
        fake = SimpleNamespace(_groups=[], _state=None)
        ChannelGroupsView._apply_value(fake, 0)   # kein Crash


class CurveDragInvalidateTest(unittest.TestCase):
    def test_right_click_delete_resets_drag_idx(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from src.ui.widgets.curve_editor import CurveEditorWidget
        from PySide6.QtCore import Qt, QPointF
        from PySide6.QtGui import QMouseEvent

        w = CurveEditorWidget()
        try:
            w.resize(200, 200)
            # 3 Punkte: Endpunkte + Mittelpunkt
            w._curve.set_points([(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)])
            w._drag_idx = 1                      # laufender Drag auf dem Mittelpunkt
            # Rechtsklick genau auf den Mittelpunkt
            mid = w._to_px(0.5, 0.5) if hasattr(w, "_to_px") else None
            if mid is None:
                # Fallback: Pixel des Mittelpunkts ueber _hit_point-Gegenprobe suchen
                from PySide6.QtCore import QPoint
                found = None
                for x in range(0, 200, 2):
                    for y in range(0, 200, 2):
                        if w._hit_point(QPoint(x, y)) == 1:
                            found = QPoint(x, y)
                            break
                    if found:
                        break
                self.assertIsNotNone(found, "Mittelpunkt nicht getroffen")
                mid = found
            ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(mid),
                             Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
                             Qt.KeyboardModifier.NoModifier)
            w.mousePressEvent(ev)
            self.assertEqual(len(w._curve.points), 2, "Punkt muss geloescht sein")
            self.assertIsNone(w._drag_idx,
                              "laufender Drag muss invalidiert sein (stale Index)")
        finally:
            w.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
