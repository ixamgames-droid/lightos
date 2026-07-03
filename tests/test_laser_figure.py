"""LAS-07a: LaserFigure-Modell (Resampling/Serialisierung/Builtins) und die
Safety-Ebene im LaserOutputManager (Arming, Not-Aus, Figur-Framequelle).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.laser.figure import (FigurePoint, LaserFigure, builtin_figures)
from src.core.laser.laser_output import LaserOutputManager


# ---------------------------------------------------------------------------
# LaserFigure
# ---------------------------------------------------------------------------

class LaserFigureTest(unittest.TestCase):
    def _square(self):
        return LaserFigure(name="Q", closed=True, points=[
            FigurePoint(-1, -1), FigurePoint(1, -1),
            FigurePoint(1, 1), FigurePoint(-1, 1)])

    def test_to_frame_resamples_to_requested_count(self):
        frame = self._square().to_frame(200, 20000)
        self.assertEqual(len(frame.points), 200)
        self.assertEqual(frame.pps, 20000)
        # Alle Punkte innerhalb des normierten Feldes.
        self.assertTrue(all(-1.0 <= p.x <= 1.0 and -1.0 <= p.y <= 1.0
                            for p in frame.points))

    def test_empty_or_single_point_yields_empty_frame(self):
        self.assertEqual(len(LaserFigure(points=[]).to_frame(100, 20000).points), 0)
        one = LaserFigure(points=[FigurePoint(0, 0)])
        self.assertEqual(len(one.to_frame(100, 20000).points), 0)

    def test_offset_and_scale(self):
        line = LaserFigure(name="L", closed=False,
                           points=[FigurePoint(-1, 0), FigurePoint(1, 0)])
        frame = line.to_frame(2, 20000, offset_x=0.0, offset_y=0.5, scale=0.5)
        # Skaliert (−0.5..+0.5) und um +0.5 in y verschoben.
        self.assertAlmostEqual(frame.points[0].x, -0.5, places=3)
        self.assertAlmostEqual(frame.points[-1].x, 0.5, places=3)
        self.assertAlmostEqual(frame.points[0].y, 0.5, places=3)

    def test_offset_clamped_to_field(self):
        line = LaserFigure(name="L", closed=False,
                           points=[FigurePoint(-1, 0), FigurePoint(1, 0)])
        frame = line.to_frame(2, 20000, offset_x=0.8, scale=1.0)
        self.assertLessEqual(max(p.x for p in frame.points), 1.0)

    def test_blank_point_blanks_segment(self):
        fig = LaserFigure(name="B", closed=False, points=[
            FigurePoint(-1, 0), FigurePoint(0, 0, blank=True),
            FigurePoint(1, 0)])
        frame = fig.to_frame(60, 20000)
        self.assertTrue(any(p.blanked for p in frame.points))
        self.assertTrue(any(not p.blanked for p in frame.points))

    def test_dict_roundtrip(self):
        fig = LaserFigure(name="Test", closed=False, points=[
            FigurePoint(0.5, -0.5, r=1.0, g=0.0, b=0.0),
            FigurePoint(-0.5, 0.5, blank=True)])
        back = LaserFigure.from_dict(fig.to_dict())
        self.assertEqual(back.name, "Test")
        self.assertFalse(back.closed)
        self.assertEqual(len(back.points), 2)
        self.assertEqual((back.points[0].r, back.points[0].g), (1.0, 0.0))
        self.assertTrue(back.points[1].blank)

    def test_builtins_present_and_valid(self):
        figs = {f.name: f for f in builtin_figures()}
        self.assertEqual(set(figs), {"Kreis", "Dreieck", "Quadrat", "Linie"})
        self.assertEqual(len(figs["Dreieck"].points), 3)
        self.assertFalse(figs["Linie"].closed)
        # Jede Builtin liefert einen nicht-leeren Frame.
        for f in figs.values():
            self.assertGreater(len(f.to_frame(120, 20000).points), 0)


# ---------------------------------------------------------------------------
# LaserOutputManager — Safety (Arming) + Figur-Framequelle
# ---------------------------------------------------------------------------

class _Fx:
    def __init__(self, fid, protocol="etherdream", net_host="10.0.0.7"):
        self.fid = fid
        self.protocol = protocol
        self.net_host = net_host


class _OM:
    def __init__(self):
        self._blackout = False


class _State:
    def __init__(self, fixtures):
        self._fixtures = fixtures
        self.programmer = {}
        self.output_manager = _OM()

    def get_patched_fixtures(self):
        return list(self._fixtures)

    def get_programmer_value(self, fid, attr, head=0):
        return self.programmer.get(fid, {}).get(attr)


class _FakeConn:
    def __init__(self, host, **kw):
        self.host = host
        self.frames = []

    def stream_frame(self, frame):
        self.frames.append(frame)
        return True

    def estop(self):
        pass

    def clear_estop(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


def _manager(fixtures):
    state = _State(fixtures)
    m = LaserOutputManager(state)
    m.connection_factory = _FakeConn
    m.idn_connection_factory = _FakeConn
    return m, state


class ArmingSafetyTest(unittest.TestCase):
    def test_starts_disarmed(self):
        m, _ = _manager([_Fx(1)])
        self.assertFalse(m.armed)

    def test_disarmed_blanks_all_output(self):
        m, state = _manager([_Fx(1)])
        state.programmer = {1: {"shutter": 255}}   # Laser wäre AN
        m._tick()                                   # aber unscharf
        frame = list(m._connections.values())[0].frames[0]
        self.assertTrue(frame.points)
        self.assertTrue(all(p.blanked for p in frame.points))

    def test_armed_emits_visible_points(self):
        m, state = _manager([_Fx(1)])
        state.programmer = {1: {"shutter": 255}}
        m.set_armed(True)
        m._tick()
        frame = list(m._connections.values())[0].frames[0]
        self.assertTrue(any(not p.blanked for p in frame.points))

    def test_armed_but_shutter_off_stays_dark(self):
        m, state = _manager([_Fx(1)])
        state.programmer = {1: {"shutter": 0}}      # Shutter-Gate zu
        m.set_armed(True)
        m._tick()
        frame = list(m._connections.values())[0].frames[0]
        self.assertTrue(all(p.blanked for p in frame.points))

    def test_estop_blanks_even_when_armed(self):
        m, state = _manager([_Fx(1)])
        state.programmer = {1: {"shutter": 255}}
        m.set_armed(True)
        m.estop_all()
        m._tick()
        # Bei estopped wird gar nicht gesendet (Verriegelung).
        conn = list(m._connections.values())[0]
        self.assertEqual(conn.frames, [])
        m.clear_estop_all()
        m._tick()
        self.assertTrue(conn.frames)


class FigureFrameSourceTest(unittest.TestCase):
    def test_default_source_is_test_pattern(self):
        m, state = _manager([_Fx(1)])
        state.programmer = {1: {"shutter": 255}}
        m.set_armed(True)
        m._tick()
        # Testmuster = Kreis: Punkte liegen ungefähr auf einem Kreis um das
        # Zentrum (Radius aus zoom-Default 128/255 ≈ 0.5).
        frame = list(m._connections.values())[0].frames[0]
        self.assertGreater(len(frame.points), 50)

    def test_set_figure_switches_source(self):
        m, state = _manager([_Fx(1)])
        state.programmer = {1: {"shutter": 255, "zoom": 255}}
        m.set_armed(True)
        # Eine Linie als Figur: alle y ~ 0 (unterscheidbar vom Kreis-Muster).
        line = LaserFigure(name="L", closed=False,
                           points=[FigurePoint(-1, 0), FigurePoint(1, 0)])
        m.set_figure(1, line)
        m._tick()
        frame = list(m._connections.values())[0].frames[0]
        self.assertTrue(all(abs(p.y) < 0.05 for p in frame.points))

    def test_clear_figure_returns_to_test_pattern(self):
        m, state = _manager([_Fx(1)])
        state.programmer = {1: {"shutter": 255}}
        m.set_armed(True)
        m.set_figure(1, LaserFigure(name="L", closed=False,
                                    points=[FigurePoint(-1, 0),
                                            FigurePoint(1, 0)]))
        m.set_figure(1, None)
        m._tick()
        frame = list(m._connections.values())[0].frames[0]
        # Kreis-Muster hat auch Punkte mit y deutlich != 0.
        self.assertTrue(any(abs(p.y) > 0.1 for p in frame.points))


if __name__ == "__main__":
    unittest.main()
