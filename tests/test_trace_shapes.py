"""Formen-Nachfahren: Form-Generatoren (Kreis/Linie/Rechteck) + trace_pan_tilt.
Korrektheit per Strahl-Rekonstruktion: der berechnete Strahl muss jeden
Form-Punkt treffen, und zwei verschieden stehende Koepfe ergeben verschiedene
Pan/Tilt-Folgen — beide treffen aber dieselbe Form.
"""
import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage.aim import (
    circle_points, line_points, rect_points, trace_pan_tilt,
    plane_basis, _mount_matrix,
)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _norm(v):
    L = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / L for c in v)


def _beam(pan, tilt, pan_range=360.0, tilt_range=180.0):
    pr = pan_range * math.pi / 360.0
    tr = tilt_range * math.pi / 360.0
    pan_rad = (pan - 128) / 128.0 * pr
    tilt_rad = (tilt - 128) / 128.0 * tr
    st, ct = math.sin(tilt_rad), math.cos(tilt_rad)
    sp, cp = math.sin(pan_rad), math.cos(pan_rad)
    local = (-st * sp, -ct, -st * cp)
    R = _mount_matrix(0, 0, 0)
    return (R[0][0]*local[0]+R[0][1]*local[1]+R[0][2]*local[2],
            R[1][0]*local[0]+R[1][1]*local[1]+R[1][2]*local[2],
            R[2][0]*local[0]+R[2][1]*local[1]+R[2][2]*local[2])


class ShapeGeneratorTest(unittest.TestCase):
    def test_circle_radius_and_coplanar(self):
        center = (0.0, 3.0, -5.0)
        normal = (0.0, 0.0, 1.0)
        pts = circle_points(center, 1.5, normal, count=24)
        self.assertEqual(len(pts), 24)
        for p in pts:
            d = math.dist(p, center)
            self.assertAlmostEqual(d, 1.5, places=6)
            # in der Ebene -> z konstant = -5
            self.assertAlmostEqual(p[2], -5.0, places=6)

    def test_line_endpoints_and_count(self):
        pts = line_points((0, 0, 0), (3, 0, 0), count=4)
        self.assertEqual(len(pts), 4)
        self.assertEqual(pts[0], (0, 0, 0))
        self.assertAlmostEqual(pts[-1][0], 3.0)
        self.assertAlmostEqual(pts[1][0], 1.0)   # gleichmaessig

    def test_rect_count_and_coplanar(self):
        pts = rect_points((0, 3, -5), 2.0, 1.0, (0, 0, 1), per_side=5)
        self.assertEqual(len(pts), 4 * 5)
        for p in pts:
            self.assertAlmostEqual(p[2], -5.0, places=6)

    def test_plane_basis_orthonormal(self):
        u, v = plane_basis((0, 0, 1))
        self.assertAlmostEqual(_dot(u, v), 0.0, places=6)
        self.assertAlmostEqual(math.sqrt(_dot(u, u)), 1.0, places=6)
        self.assertAlmostEqual(math.sqrt(_dot(v, v)), 1.0, places=6)


class TracePanTiltTest(unittest.TestCase):
    def test_circle_trace_beams_hit_each_point(self):
        pos = (2.0, 5.0, 0.0)
        center = (0.0, 3.0, -5.0)
        pts = circle_points(center, 1.0, (0, 0, 1), count=16)
        seq = trace_pan_tilt(pos, pts)
        self.assertEqual(len(seq), 16)
        for (pan, tilt), p in zip(seq, pts):
            beam = _norm(_beam(pan, tilt))
            want = _norm(tuple(t - q for t, q in zip(p, pos)))
            self.assertGreater(_dot(beam, want), 0.999)

    def test_two_fixtures_different_sequences_same_shape(self):
        center = (0.0, 3.0, -5.0)
        pts = circle_points(center, 1.0, (0, 0, 1), count=12)
        left = trace_pan_tilt((-3.0, 5.0, 0.0), pts)
        right = trace_pan_tilt((3.0, 5.0, 0.0), pts)
        # Verschiedene Standorte -> verschiedene Pan/Tilt-Folgen
        self.assertNotEqual(left, right)
        # ... aber beide treffen jeden Punkt
        for pos, seq in (((-3.0, 5.0, 0.0), left), ((3.0, 5.0, 0.0), right)):
            for (pan, tilt), p in zip(seq, pts):
                beam = _norm(_beam(pan, tilt))
                want = _norm(tuple(t - q for t, q in zip(p, pos)))
                self.assertGreater(_dot(beam, want), 0.999)


if __name__ == "__main__":
    unittest.main()
