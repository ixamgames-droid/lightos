"""Etappe A (VC-Live-Editor-Ausbau) — ``dimmer_levels`` als ``dimmer_sequence``-
ParamSpec, symmetrisch zum bestehenden ``colors``/``color_sequence``-Muster.

Prueft:
- ``list_params()`` liefert den Spec NUR bei DIMMER + CHASE + dimmer_cycle=True
  (exakt gespiegelt zum Renderer-Gate ``rgb_matrix.py:601/1036-1037``).
- RGB-Matrizen (und Dimmer ohne Chase/dimmer_cycle) bekommen KEINEN Spec.
- ``effect_live.get_param("dimmer_levels", fid)`` liefert das LIVE-
  ``DimmerSequence``-Objekt (keine Kopie, direkte Mutation erlaubt).
- ``effect_live.set_param_normalized``/``adjust_param`` blocken den neuen Kind
  genau wie ``color_sequence`` (nicht-numerisch, kein Fader/Encoder-Ziel).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from src.core.engine import effect_live
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle, DimmerSequence


def _dimmer_chase_matrix(fm, name, dimmer_cycle=True):
    m = fm.new_rgb_matrix(name)
    m.style = MatrixStyle.DIMMER
    m.algorithm = RgbAlgorithm.CHASE
    m.params["dimmer_cycle"] = dimmer_cycle
    return m


class TestDimmerLevelsParamSpec(unittest.TestCase):
    def setUp(self):
        effect_live.clear_live_overrides()
        try:
            from src.core.engine.tempo_bus import reset_tempo_bus_manager
            reset_tempo_bus_manager()
        except Exception:
            pass
        self.fm = get_function_manager()

    def _spec(self, m, key="dimmer_levels"):
        return next((s for s in m.list_params() if s.key == key), None)

    def test_rgb_matrix_has_no_dimmer_levels_spec(self):
        m = self.fm.new_rgb_matrix("RGB")
        m.style = MatrixStyle.RGB
        m.algorithm = RgbAlgorithm.CHASE
        self.assertIsNone(self._spec(m))
        # Zum Vergleich: colors-Spec ist bei RGB+CHASE vorhanden.
        self.assertIsNotNone(self._spec(m, "colors"))

    def test_dimmer_chase_cycle_true_has_spec(self):
        m = _dimmer_chase_matrix(self.fm, "DimChase", dimmer_cycle=True)
        spec = self._spec(m)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.kind, "dimmer_sequence")
        self.assertTrue(spec.live_editable)
        self.assertTrue(spec.mappable)

    def test_dimmer_cycle_false_has_no_spec(self):
        m = _dimmer_chase_matrix(self.fm, "DimNoCycle", dimmer_cycle=False)
        self.assertIsNone(self._spec(m))

    def test_dimmer_style_non_chase_has_no_spec(self):
        m = self.fm.new_rgb_matrix("DimWave")
        m.style = MatrixStyle.DIMMER
        m.algorithm = RgbAlgorithm.WAVE
        m.params["dimmer_cycle"] = True
        self.assertIsNone(self._spec(m))

    def test_set_param_normalized_blocks_dimmer_sequence(self):
        m = _dimmer_chase_matrix(self.fm, "DimChase2", dimmer_cycle=True)
        effect_live.begin_live_edit(m.id)
        self.assertFalse(
            effect_live.set_param_normalized("dimmer_levels", 0.5, m.id))

    def test_adjust_param_blocks_dimmer_sequence(self):
        m = _dimmer_chase_matrix(self.fm, "DimChase3", dimmer_cycle=True)
        effect_live.begin_live_edit(m.id)
        self.assertFalse(
            effect_live.adjust_param("dimmer_levels", 0.1, m.id))

    def test_get_param_returns_live_dimmer_sequence(self):
        m = _dimmer_chase_matrix(self.fm, "DimChase4", dimmer_cycle=True)
        m.dimmer_levels = DimmerSequence([255, 50, 100])
        effect_live.begin_live_edit(m.id)
        seq = effect_live.get_param("dimmer_levels", m.id)
        self.assertIs(seq, m.dimmer_levels)
        self.assertEqual(seq.all_levels(), [255, 50, 100])
        # Direkte Mutation am zurueckgegebenen Objekt wirkt sofort aufs Original.
        seq.set_level(0, 10)
        self.assertEqual(m.dimmer_levels.level_at(0), 10)


if __name__ == "__main__":
    unittest.main()
