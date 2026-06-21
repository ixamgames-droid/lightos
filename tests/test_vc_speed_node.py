"""Phase C: VCSpeedDial als Speed-Knoten (QLC+-Parität, Master/Sub).

Siehe docs/SPEED_MASTER_SUB_PLAN.md. Im Modus SpeedTarget.SPEED_NODE konfiguriert der
Dial direkt einen Tempo-Bus: Master (eigene BPM via Tap/Rad) oder Sub (folgt einem
Master mit dem Faktor-Gitter ¼ ½ 1 2 4). Headless, Qt offscreen.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.ui.virtualconsole.vc_speedial import (
    VCSpeedDial, SpeedTarget, DEFAULT_FACTORS, _fmt_factor, _parse_factor_token,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class SpeedNodeTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_tempo_bus_manager()
        get_bpm_manager().reset()
        self.mgr = get_tempo_bus_manager()

    def tearDown(self):
        reset_tempo_bus_manager()
        get_bpm_manager().reset()

    # ── Master ────────────────────────────────────────────────────────────────

    def test_master_node_sets_bus_bpm(self):
        w = VCSpeedDial("Speed A")
        w.target_mode = SpeedTarget.SPEED_NODE
        w.role = "master"
        w.tempo_bus_id = "A"
        w.bpm = 130                          # Setter -> _apply -> bus.set_bpm
        bus = self.mgr.ensure_bus("A")
        self.assertEqual(bus.role, "master")
        self.assertAlmostEqual(bus.bpm, 130.0, places=3)

    def test_master_tap_taps_bus(self):
        w = VCSpeedDial("Speed A")
        w.target_mode = SpeedTarget.SPEED_NODE
        w.role = "master"
        w.tempo_bus_id = "A"
        w._tap()
        w._tap()
        bus = self.mgr.ensure_bus("A")
        self.assertGreater(bus.bpm, 0.0)

    # ── Sub ───────────────────────────────────────────────────────────────────

    def test_sub_node_follows_parent_with_factor(self):
        m = self.mgr.ensure_bus("M")
        m.set_bpm(120)
        w = VCSpeedDial("Speed S")
        w.target_mode = SpeedTarget.SPEED_NODE
        w.role = "sub"
        w.tempo_bus_id = "S"
        w.parent_bus_id = "M"
        w._ensure_node_config()
        w._set_factor(0.5)
        s = self.mgr.ensure_bus("S")
        self.assertEqual(s.role, "sub")
        self.assertEqual(s.parent_id, "M")
        self.assertAlmostEqual(s.bus_multiplier, 0.5, places=6)
        for _ in range(10):
            self.mgr.advance_frame(0.1)      # 1.0s @120 -> M 2.0
        self.assertAlmostEqual(m.position(), 2.0, places=6)
        self.assertAlmostEqual(s.position(), 1.0, places=6)

    def test_factor_grid_click_sets_multiplier(self):
        m = self.mgr.ensure_bus("M")
        m.set_bpm(120)
        w = VCSpeedDial("Speed S")
        w.resize(200, 160)
        w.target_mode = SpeedTarget.SPEED_NODE
        w.role = "sub"
        w.tempo_bus_id = "S"
        w.parent_bus_id = "M"
        w._ensure_node_config()
        # Klick auf den ½-Button (Faktor 0.5) im Gitter.
        target_rect = None
        for rect, f in w._factor_rects():
            if abs(f - 0.5) < 1e-6:
                target_rect = rect
                break
        assert target_rect is not None
        center = target_rect.center()
        handled = w._node_sub_click(QPoint(center.x(), center.y()))
        self.assertTrue(handled)
        self.assertAlmostEqual(w._active_factor, 0.5, places=6)
        self.assertAlmostEqual(self.mgr.ensure_bus("S").bus_multiplier, 0.5, places=6)

    def test_step_and_reset_factor(self):
        w = VCSpeedDial("Speed S")
        w.target_mode = SpeedTarget.SPEED_NODE
        w.role = "sub"
        w.tempo_bus_id = "S"
        # Default-Set ¼ ½ 1 2 4, Start 1.0
        self.assertAlmostEqual(w._active_factor, 1.0)
        w._step_factor(+1)
        self.assertAlmostEqual(w._active_factor, 2.0)
        w._step_factor(-1)
        self.assertAlmostEqual(w._active_factor, 1.0)
        w._step_factor(-1)
        self.assertAlmostEqual(w._active_factor, 0.5)
        w._reset_factor()
        self.assertAlmostEqual(w._active_factor, 1.0)

    def test_sub_sync_resets_downbeat(self):
        m = self.mgr.ensure_bus("M")
        m.set_bpm(120)
        w = VCSpeedDial("Speed S")
        w.target_mode = SpeedTarget.SPEED_NODE
        w.role = "sub"
        w.tempo_bus_id = "S"
        w.parent_bus_id = "M"
        w._ensure_node_config()
        for _ in range(10):
            self.mgr.advance_frame(0.1)
        s = self.mgr.ensure_bus("S")
        self.assertGreater(s.position(), 0.5)
        w._node_sync()                       # Downbeat neu setzen
        self.assertAlmostEqual(s.position(), 0.0, places=6)

    # ── Persistenz + Helfer ────────────────────────────────────────────────────

    def test_roundtrip(self):
        w = VCSpeedDial("Speed S")
        w.target_mode = SpeedTarget.SPEED_NODE
        w.role = "sub"
        w.tempo_bus_id = "S"
        w.parent_bus_id = "M"
        w.factor_buttons = [0.25, 0.5, 1.0, 2.0, 4.0]
        w._active_factor = 0.5
        w.show_dial = False
        w.show_sync = False
        d = w.to_dict()

        w2 = VCSpeedDial("x")
        w2.apply_dict(d)
        self.assertEqual(w2.target_mode, SpeedTarget.SPEED_NODE)
        self.assertEqual(w2.role, "sub")
        self.assertEqual(w2.parent_bus_id, "M")
        self.assertEqual(w2.factor_buttons, [0.25, 0.5, 1.0, 2.0, 4.0])
        self.assertAlmostEqual(w2._active_factor, 0.5)
        self.assertFalse(w2.show_dial)
        self.assertFalse(w2.show_sync)
        self.assertTrue(w2.show_bpm)

    def test_legacy_dict_defaults_to_master(self):
        """Alt-SpeedDial ohne Phase-C-Keys -> Master, Default-Faktoren, alles sichtbar."""
        w = VCSpeedDial("x")
        w.apply_dict({"bpm": 120.0, "target_mode": SpeedTarget.EXECUTOR})
        self.assertEqual(w.role, "master")
        self.assertEqual(w.parent_bus_id, "")
        self.assertEqual(w.factor_buttons, list(DEFAULT_FACTORS))
        self.assertTrue(w.show_dial and w.show_bpm)

    def test_fmt_and_parse_factor(self):
        self.assertEqual(_fmt_factor(0.25), "¼")
        self.assertEqual(_fmt_factor(0.5), "½")
        self.assertEqual(_fmt_factor(2.0), "2×")
        self.assertEqual(_fmt_factor(1.0), "1×")
        for tok, expected in (("¼", 0.25), ("1/2", 0.5), ("2×", 2.0), ("0.25", 0.25)):
            v = _parse_factor_token(tok)
            assert v is not None
            self.assertAlmostEqual(v, expected)
        self.assertIsNone(_parse_factor_token(""))


if __name__ == "__main__":
    unittest.main()
