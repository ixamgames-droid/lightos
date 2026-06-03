"""Tests fuer Matrix-Grid mit Luecken (None-Eintraege in fixture_grid).

Prueft:
  A) Luecke wird nicht in DMX geschrieben (kein Crash, kein Fixture fuer idx 1).
  B) _render liefert volles Grid inkl. Luecke (Laenge == cols*rows).
  C) Persistenz-Round-Trip: to_dict/from_dict rundet None korrekt.
  D) Migration: dichte Liste (ohne None) laedt unveraendert und schreibt alle Fixtures.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle
from src.core.dmx.universe import Universe


class _Ch:
    def __init__(self, attribute, channel_number):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = 0


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 3

    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


def _make_matrix_gap():
    """3×1-Matrix mit Luecke in der Mitte: fids [10, None, 12]."""
    m = RgbMatrixInstance(
        name="t",
        cols=3,
        rows=1,
        fixture_grid=[10, None, 12],
        algorithm=RgbAlgorithm.PLAIN,
        color1=(255, 0, 0),
    )
    m.style = MatrixStyle.RGB
    m.drive_intensity = True
    m.start()
    return m


class RgbMatrixGapsTest(unittest.TestCase):

    def setUp(self):
        self._orig = A.get_channels_for_patched
        # Drei Kanaele: color_r/g/b
        A.get_channels_for_patched = lambda fx: [
            _Ch("color_r", 1),
            _Ch("color_g", 2),
            _Ch("color_b", 3),
        ]
        self.m = _make_matrix_gap()

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    # A) Luecke wird nicht geschrieben ─────────────────────────────────────────
    def test_gap_not_written(self):
        """Kanal von fid10 und fid12 werden rot geschrieben; kein Crash fuer Luecke."""
        universes = {1: Universe(1)}
        # NUR Fixtures fuer fid 10 und 12; kein Fixture fuer Luecke (idx 1)
        patch_cache = [_Fx(10, 1, 1), _Fx(12, 1, 10)]
        self.m.write(universes, patch_cache, 0.0)
        u = universes[1]
        # fid10: color_r an Adresse 1 (address=1, channel_number=1 => addr 1)
        self.assertEqual(u.get_channel(1), 255, "fid10 color_r muss 255 sein")
        # fid12: color_r an Adresse 10 (address=10, channel_number=1 => addr 10)
        self.assertEqual(u.get_channel(10), 255, "fid12 color_r muss 255 sein")

    # B) _render liefert volles Grid inkl. Luecke ──────────────────────────────
    def test_render_includes_gap(self):
        """_render liefert immer cols*rows Pixel (Luecke ist ein echter Pixel)."""
        pixels = self.m._render(0.0)
        self.assertEqual(len(pixels), 3, "_render muss 3 Pixel (cols=3, rows=1) liefern")

    # C) Persistenz-Round-Trip ─────────────────────────────────────────────────
    def test_roundtrip_preserves_none(self):
        """to_dict/from_dict erhaelt None-Eintraege (JSON null -> None)."""
        restored = RgbMatrixInstance.from_dict(self.m.to_dict())
        self.assertEqual(restored.fixture_grid, [10, None, 12],
                         "fixture_grid mit None muss round-trippen")

    # D) Migration dichte Liste ────────────────────────────────────────────────
    def test_dense_migration(self):
        """Alte dichte Liste (ohne None) laedt unveraendert und schreibt alle Fixtures."""
        d = {
            "name": "dense",
            "cols": 3,
            "rows": 1,
            "fixture_grid": [10, 11, 12],
            "algorithm": "Plain",
            "color1": [255, 0, 0],
        }
        m = RgbMatrixInstance.from_dict(d)
        m.style = MatrixStyle.RGB
        m.drive_intensity = True
        m.start()
        self.assertEqual(m.fixture_grid, [10, 11, 12],
                         "dichte Liste muss unveraendert uebernommen werden")

        universes = {1: Universe(1)}
        patch_cache = [_Fx(10, 1, 1), _Fx(11, 1, 10), _Fx(12, 1, 20)]
        m.write(universes, patch_cache, 0.0)
        u = universes[1]
        self.assertEqual(u.get_channel(1),  255, "fid10 color_r")
        self.assertEqual(u.get_channel(10), 255, "fid11 color_r")
        self.assertEqual(u.get_channel(20), 255, "fid12 color_r")


if __name__ == "__main__":
    unittest.main()
