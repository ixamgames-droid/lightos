"""Codex-Follow-up-Befunde auf #87-#90 (ENG-09, ENG-10, UI-14, DEMO-06).

- ENG-09: classify_attr strippt das Mehrkopf-Suffix (attr#N) -> prism_rotation#1
  landet in Effect, nicht ueber den Substring 'prism' in Beam.
- ENG-10: RgbMatrixInstance.sync_phase loescht _last_bus_pos, sonst ueberspringt
  der DEMO-04-Stall-Check nach einem Sync die Bus-Synchronisation.
- UI-14: VCButton-Farb-Badge invalidiert seinen Cache, wenn die ColorSequence
  eines gebundenen Effekts live geaendert wird.
- DEMO-06: ein als Modul importierter Generator (python -c "import tools.build_x")
  kann _gen_env aufloesen (tools/__init__ legt tools/ auf sys.path).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.attr_groups import classify_attr
from src.core.engine.tempo_bus import (get_tempo_bus_manager,
                                        reset_tempo_bus_manager)
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.rgb_matrix import (RgbMatrixInstance, RgbAlgorithm,
                                        ColorSequence)
from src.core.app_state import get_state
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction

_app = QApplication.instance() or QApplication([])


class ENG09ClassifyStripsHeadSuffix(unittest.TestCase):
    def test_suffixed_prism_rotation_is_effect(self):
        self.assertEqual(classify_attr("prism_rotation"), "Effect")
        self.assertEqual(classify_attr("prism_rotation#1"), "Effect")
        self.assertEqual(classify_attr("prism_rotation#2"), "Effect")

    def test_suffix_never_changes_group(self):
        for attr in ("color_r", "pan", "tilt", "shutter", "zoom", "intensity",
                     "gobo_wheel", "macro"):
            self.assertEqual(
                classify_attr(attr + "#1"), classify_attr(attr),
                f"{attr}#1 muss dieselbe Gruppe wie {attr} liefern (ENG-09)")


class ENG10SyncPhaseResetsStallCache(unittest.TestCase):
    def setUp(self):
        reset_tempo_bus_manager()
        get_bpm_manager().reset()

    def tearDown(self):
        reset_tempo_bus_manager()
        get_bpm_manager().reset()

    def test_sync_phase_clears_last_bus_pos(self):
        mgr = get_tempo_bus_manager()
        mgr.ensure_bus("A").set_bpm(120.0)
        for _ in range(5):
            mgr.advance_frame(0.05)   # Bus auf eine Position > 0 bringen
        m = RgbMatrixInstance(cols=4, rows=1, algorithm=RgbAlgorithm.COLORFADE,
                              fixture_grid=[1, 2, 3, 4])
        m.colors = ColorSequence([(255, 0, 0), (0, 255, 0)])
        m.tempo_bus_id = "A"
        m._beat_anchor = 0.0
        # 1. Frame: gegen den Bus rendern -> _last_bus_pos == aktuelle Bus-Position.
        m._advance_step(0.05)
        first = m._last_bus_pos
        self.assertIsNotNone(first, "erster Frame muss die Bus-Position cachen")
        # 2. Frame OHNE advance_frame -> Bus steht -> Stall-Zweig, _last_bus_pos bleibt.
        m._advance_step(0.05)
        self.assertEqual(m._last_bus_pos, first,
                         "stehender Bus -> _last_bus_pos unveraendert (Stall)")
        # sync_phase MUSS den Stall-Cache loeschen (ENG-10), sonst free-runt der
        # naechste Frame statt den frisch gesetzten Anker bus-synchron zu rechnen.
        m.sync_phase()
        self.assertIsNone(m._last_bus_pos,
                          "sync_phase muss _last_bus_pos zuruecksetzen (ENG-10)")


class UI14BadgeCacheInvalidatesOnLiveColorEdit(unittest.TestCase):
    def setUp(self):
        self.fm = get_state().function_manager
        self.fn = self.fm.new_rgb_matrix("FollowupBadgeMatrix")

    def tearDown(self):
        try:
            self.fm.remove(self.fn.id)
        except Exception:
            pass

    def test_cache_invalidates_when_sequence_changes(self):
        b = VCButton("FX")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fn.id
        first = b._color_badge_colors()
        self.assertEqual(len(first), 3, "frische Matrix hat 3 Default-Farben")
        # Live-Edit der ColorSequence (wie VCColor EFFECT / add_color / toggle_color).
        self.fn.colors = ColorSequence([(10, 20, 30)])
        second = b._color_badge_colors()
        self.assertEqual(
            len(second), 1,
            "UI-14: nach Live-Color-Edit muss der Badge-Cache invalidieren und die "
            "neue (einfarbige) Sequence zeigen, nicht die 3 alten Farben")

    def test_unchanged_binding_still_cached(self):
        b = VCButton("FX")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fn.id
        b._color_badge_colors()
        key1 = b._badge_cache_key
        b._color_badge_colors()
        self.assertEqual(b._badge_cache_key, key1,
                         "ohne Aenderung bleibt der Cache-Key stabil (kein Flackern)")


class DEMO06GenEnvModuleImport(unittest.TestCase):
    def test_gen_env_resolvable_via_package_import(self):
        import subprocess
        import sys
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = subprocess.run(
            [sys.executable, "-c", "import tools; import _gen_env; print('GEN_OK')"],
            cwd=repo, capture_output=True, text=True, timeout=60)
        self.assertIn("GEN_OK", r.stdout,
                      "tools/__init__ muss tools/ auf sys.path legen, damit der "
                      "Modul-Import-Pfad _gen_env aufloest (DEMO-06). "
                      f"stdout={r.stdout!r} stderr={r.stderr!r}")


if __name__ == "__main__":
    unittest.main()
