"""EFX – Verhältnis der Geräte zueinander.

Deckt das neue Geräte-Verhältnis ab: phase_mode (sync/fan/offset),
phase_offset_deg, counter_rotate (gegenläufig) — in der Engine (Phasen-Mathe,
set_param/get_param, Persistenz) UND im Editor/Großansicht (bidirektionaler
Sync, kontextabhängiges Aktivieren der Regler).
"""
import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm


def _circle(**kw):
    e = EfxInstance("rel")
    e.algorithm = EfxAlgorithm.CIRCLE
    e.width = e.height = 100.0
    e.x_offset = e.y_offset = 128.0
    e.bit16 = False                      # saubere 8-bit-Werte für Vergleiche
    e.fixtures = [EfxFixture(fid=1), EfxFixture(fid=2)]
    for k, v in kw.items():
        setattr(e, k, v)
    return e


class EngineFanForTest(unittest.TestCase):
    def test_sync_zero_offset(self):
        e = _circle(phase_mode="sync")
        self.assertEqual([e._fan_for(i, 4) for i in range(4)], [0, 0, 0, 0])

    def test_fan_even_distribution(self):
        e = _circle(phase_mode="fan", spread=1.0)
        self.assertEqual([e._fan_for(i, 4) for i in range(4)],
                         [0.0, 0.25, 0.5, 0.75])

    def test_offset_degrees(self):
        e = _circle(phase_mode="offset", phase_offset_deg=90.0)
        # 90° = 0.25 Zyklus pro Gerät
        self.assertEqual([e._fan_for(i, 3) for i in range(3)],
                         [0.0, 0.25, 0.5])

    def test_single_fixture_no_offset(self):
        e = _circle(phase_mode="fan", spread=1.0)
        self.assertEqual(e._fan_for(0, 1), 0.0)


class EnginePhaseTest(unittest.TestCase):
    def test_sync_both_heads_identical(self):
        e = _circle(phase_mode="sync")
        for k in range(8):
            e._phase = k / 8.0
            v = e._values()
            self.assertEqual(v[1]["pan"], v[2]["pan"])
            self.assertEqual(v[1]["tilt"], v[2]["tilt"])

    def test_fan_second_head_half_cycle(self):
        e = _circle(phase_mode="fan", spread=1.0)
        e._phase = 0.1
        v = e._values()
        # Kopf 2 läuft mit Phase 0.1 + 0.5 (Fan bei 2 Köpfen, spread 1)
        ref = e._calc((0.1 + 0.5) % 1.0)
        self.assertAlmostEqual(v[2]["pan"], int(ref[0]), delta=1)
        self.assertAlmostEqual(v[2]["tilt"], int(ref[1]), delta=1)

    def test_offset_second_head_shifted(self):
        e = _circle(phase_mode="offset", phase_offset_deg=90.0)
        e._phase = 0.2
        v = e._values()
        ref = e._calc((0.2 + 0.25) % 1.0)   # 90° = 0.25
        self.assertAlmostEqual(v[2]["pan"], int(ref[0]), delta=1)
        self.assertAlmostEqual(v[2]["tilt"], int(ref[1]), delta=1)

    def test_counter_rotate_opposite_direction(self):
        # Gegenläufig + synchron: Kopf 2 fährt den Kreis rückwärts.
        # Auf dem Kreis heißt das: gleiche Pan-Achse, an cy gespiegelte Tilt.
        e = _circle(phase_mode="sync", counter_rotate=True)
        e._phase = 0.1
        v = e._values()
        self.assertAlmostEqual(v[1]["pan"], v[2]["pan"], delta=1)
        self.assertAlmostEqual(v[2]["tilt"] - 128, -(v[1]["tilt"] - 128), delta=2)

    def test_counter_rotate_even_head_unchanged(self):
        e = _circle(phase_mode="sync", counter_rotate=True)
        e._phase = 0.37
        v = e._values()
        ref = e._calc(0.37)               # Kopf 1 (gerader Index) läuft vorwärts
        self.assertAlmostEqual(v[1]["pan"], int(ref[0]), delta=1)
        self.assertAlmostEqual(v[1]["tilt"], int(ref[1]), delta=1)


class EngineParamPersistenceTest(unittest.TestCase):
    def test_set_get_param_roundtrip(self):
        e = _circle()
        self.assertTrue(e.set_param("phase_mode", "offset"))
        self.assertEqual(e.get_param("phase_mode"), "offset")
        self.assertTrue(e.set_param("phase_offset_deg", 45))
        self.assertEqual(e.get_param("phase_offset_deg"), 45.0)
        self.assertTrue(e.set_param("counter_rotate", True))
        self.assertIs(e.get_param("counter_rotate"), True)

    def test_set_param_invalid_mode_falls_back(self):
        e = _circle()
        e.set_param("phase_mode", "quatsch")
        self.assertEqual(e.phase_mode, "fan")

    def test_offset_wraps_360(self):
        e = _circle()
        e.set_param("phase_offset_deg", 375)
        self.assertAlmostEqual(e.phase_offset_deg, 15.0, delta=0.001)

    def test_toggle_counter_action(self):
        e = _circle(counter_rotate=False)
        self.assertTrue(e.do_action("toggle_counter"))
        self.assertTrue(e.counter_rotate)
        self.assertTrue(e.do_action("toggle_counter"))
        self.assertFalse(e.counter_rotate)

    def test_to_from_dict_roundtrip(self):
        e = _circle(phase_mode="offset", phase_offset_deg=33.0, counter_rotate=True)
        d = e.to_dict()
        self.assertEqual(d["phase_mode"], "offset")
        self.assertEqual(d["phase_offset_deg"], 33.0)
        self.assertTrue(d["counter_rotate"])
        e2 = EfxInstance.from_dict(d)
        self.assertEqual(e2.phase_mode, "offset")
        self.assertEqual(e2.phase_offset_deg, 33.0)
        self.assertTrue(e2.counter_rotate)

    def test_legacy_dict_defaults_to_fan(self):
        # Alt-Show ohne die neuen Felder → "fan"/0/False, Verhalten unverändert.
        e = EfxInstance.from_dict({"name": "alt", "algorithm": "Circle", "spread": 1.0})
        self.assertEqual(e.phase_mode, "fan")
        self.assertEqual(e.phase_offset_deg, 0.0)
        self.assertFalse(e.counter_rotate)


# ── UI: Editor + Großansicht ────────────────────────────────────────────────
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

from src.ui.views.efx_view import EfxView  # noqa: E402


class ViewRelationshipTest(unittest.TestCase):
    def setUp(self):
        self.v = EfxView()
        self.v._add_efx()
        self.cur = self.v._current
        self.assertIsNotNone(self.cur)

    def test_set_relationship_updates_model_and_widgets(self):
        self.v._set_relationship("phase_mode", "offset")
        self.assertEqual(self.cur.phase_mode, "offset")
        self.assertEqual(self.v._phase_mode_combo.currentData(), "offset")
        # Im Offset-Modus ist der Gradversatz aktiv, die Fächer-Streuung nicht.
        self.assertTrue(self.v._offset_spin.isEnabled())
        self.assertFalse(self.v._spread_spin.isEnabled())

    def test_offset_and_counter_roundtrip(self):
        self.v._set_relationship("phase_offset_deg", 60)
        self.assertEqual(self.cur.phase_offset_deg, 60.0)
        self.assertEqual(self.v._offset_spin.value(), 60.0)
        self.v._set_relationship("counter_rotate", True)
        self.assertTrue(self.cur.counter_rotate)
        self.assertTrue(self.v._counter_chk.isChecked())

    def test_fan_mode_enables_spread(self):
        self.v._set_relationship("phase_mode", "fan")
        self.assertTrue(self.v._spread_spin.isEnabled())
        self.assertFalse(self.v._offset_spin.isEnabled())

    def test_load_to_ui_reflects_relationship(self):
        self.cur.phase_mode = "offset"
        self.cur.phase_offset_deg = 75.0
        self.cur.counter_rotate = True
        self.cur.mirror = True
        self.v._load_to_ui(self.cur)
        self.assertEqual(self.v._phase_mode_combo.currentData(), "offset")
        self.assertEqual(self.v._offset_spin.value(), 75.0)
        self.assertTrue(self.v._counter_chk.isChecked())
        self.assertTrue(self.v._mirror_chk.isChecked())

    def test_popout_relationship_bidirectional(self):
        self.v._open_popout()
        po = self.v._popout
        self.assertIsNotNone(po)
        # Popout → Modell + Editor
        po._mode_combo.setCurrentIndex(po._mode_combo.findData("sync"))
        self.assertEqual(self.cur.phase_mode, "sync")
        self.assertEqual(self.v._phase_mode_combo.currentData(), "sync")
        # Editor → Popout
        self.v._set_relationship("counter_rotate", True)
        self.assertTrue(po._rel_counter.isChecked())
        self.v._on_popout_closed()


if __name__ == "__main__":
    unittest.main()
