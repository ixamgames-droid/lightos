"""Tests fuer den Live-Programming-Dispatcher effect_live + Live-Override (Phase 6).

Prueft die gemeinsame Schicht, die VC und MIDI nutzen: Parameter live setzen
(absolut/normalisiert/relativ), Aktionen ausloesen, Color-Picker in die Sequence,
sowie das Live-Override-Modell (snapshot/clear/commit) und Freeze.
"""
import unittest

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, ColorSequence
from src.core.engine import effect_live


class EffectLiveTest(unittest.TestCase):

    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="live", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    # ── Ziel-Aufloesung ───────────────────────────────────────────────────────
    def test_resolve_explicit_and_active(self):
        self.assertIs(effect_live.resolve_target(self.m.id), self.m)
        self.fm.start(self.m.id)
        self.assertIs(effect_live.resolve_target(None), self.m)  # aktiver Effekt

    # ── set_param_normalized: Wertebereiche ───────────────────────────────────
    def test_normalized_float(self):
        effect_live.set_param_normalized("speed", 0.5, self.m.id)
        self.assertAlmostEqual(self.m.matrix_speed, 0.01 + (20.0 - 0.01) * 0.5, places=2)

    def test_normalized_int(self):
        effect_live.set_param_normalized("runner_count", 1.0, self.m.id)
        self.assertEqual(self.m.params["runner_count"], 16)   # max der Spec

    def test_normalized_select(self):
        effect_live.set_param_normalized("movement", 1.0, self.m.id)
        self.assertEqual(self.m.params["movement"], "outside_in")  # letzte Option

    def test_normalized_fill_speed_live(self):
        # Float-Param live ueber einen normierten Wert (0..1) auf den Bereich
        # abbilden (WP-3: Fill ist zeitbasiert, fill_speed-Bereich 0.05..10).
        self.m.algorithm = RgbAlgorithm.FILL
        effect_live.set_param_normalized("fill_speed", 0.5, self.m.id)
        self.assertAlmostEqual(self.m.params["fill_speed"], 5.025, places=2)

    # ── relativ (Encoder) ──────────────────────────────────────────────────────
    def test_adjust_relative_clamped(self):
        self.m.matrix_speed = 5.0
        effect_live.adjust_param("speed", 0.1, self.m.id)
        self.assertGreater(self.m.matrix_speed, 5.0)
        # nach oben geklemmt
        for _ in range(50):
            effect_live.adjust_param("speed", 0.5, self.m.id)
        self.assertLessEqual(self.m.matrix_speed, 20.0)

    # ── Aktionen + Farben ──────────────────────────────────────────────────────
    def test_do_action_add_color(self):
        self.m.colors = ColorSequence([(255, 0, 0)])
        effect_live.do_action("add_color", self.m.id, rgb=(0, 255, 0))
        self.assertEqual(self.m.colors.all_colors(), [(255, 0, 0), (0, 255, 0)])

    def test_do_action_clear_colors(self):
        """clear_colors leert die Live-Farbliste (anders als clear_live_override,
        das auf den Preset zuruecksetzt) — Basis fuer den Live-Color-Chase-Aufbau."""
        self.m.colors = ColorSequence([(255, 0, 0), (0, 255, 0)])
        self.assertTrue(effect_live.do_action("clear_colors", self.m.id))
        self.assertEqual(len(self.m.colors), 0)
        # danach live neu aufbauen (wie Pad-Druecke auf der Color-Chase-Seite)
        effect_live.do_action("add_color", self.m.id, rgb=(0, 0, 255))
        effect_live.do_action("add_color", self.m.id, rgb=(255, 255, 0))
        self.assertEqual(self.m.colors.all_colors(), [(0, 0, 255), (255, 255, 0)])

    def test_set_selected_color(self):
        self.m.colors = ColorSequence([(255, 0, 0), (0, 0, 255)])
        self.m.colors.active_index = 1
        effect_live.set_selected_color((9, 9, 9), self.m.id)
        self.assertEqual(self.m.colors.color_at(1), (9, 9, 9))

    def test_active_target_when_no_id(self):
        self.fm.start(self.m.id)
        effect_live.set_param_normalized("speed", 1.0, None)   # aktiver Effekt
        self.assertGreater(self.m.matrix_speed, 15)

    # ── Live-Override-Modell (#17) ──────────────────────────────────────────────
    def test_clear_live_override_restores_preset(self):
        self.m.matrix_speed = 1.0
        self.m.snapshot_preset()
        effect_live.set_param_normalized("speed", 1.0, self.m.id)
        self.assertGreater(self.m.matrix_speed, 15)
        self.m.clear_live_override()
        self.assertEqual(self.m.matrix_speed, 1.0)             # zurueck auf Preset

    def test_commit_live_to_preset(self):
        self.m.matrix_speed = 1.0
        self.m.snapshot_preset()
        self.m.matrix_speed = 7.0
        self.m.commit_live_to_preset()                          # 7.0 ist neuer Preset
        self.m.matrix_speed = 2.0
        self.m.clear_live_override()
        self.assertEqual(self.m.matrix_speed, 7.0)

    def test_live_color_add_then_clear(self):
        self.m.colors = ColorSequence([(255, 0, 0), (0, 0, 255)])
        self.m.snapshot_preset()
        effect_live.do_action("add_color", self.m.id, rgb=(0, 255, 0))
        self.assertEqual(len(self.m.colors), 3)
        self.m.clear_live_override()
        self.assertEqual(self.m.colors.all_colors(), [(255, 0, 0), (0, 0, 255)])

    # ── Freeze ──────────────────────────────────────────────────────────────────
    def test_freeze_stops_phase(self):
        self.m.start()
        self.m.matrix_speed = 2.0
        self.m._step = 0.0
        self.m.write({}, [], 1.0)
        self.assertAlmostEqual(self.m._step, 2.0)               # laeuft
        effect_live.do_action("toggle_freeze", self.m.id)
        self.assertTrue(self.m._frozen)
        self.m.write({}, [], 1.0)
        self.assertAlmostEqual(self.m._step, 2.0)               # eingefroren: unveraendert


if __name__ == "__main__":
    unittest.main()
