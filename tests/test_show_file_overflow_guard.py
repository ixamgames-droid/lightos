"""A3D-19: Ein einzelner Overflow-Wert (1e999 -> float inf) beim Show-Load darf
NICHT den gesamten Programmer / alle Base-Levels loeschen.

`json.loads('1e999')` ergibt `float('inf')`; `int(float('inf'))` wirft
`OverflowError` (NICHT `ValueError`). Der Per-Wert-Guard fing bisher nur
`(TypeError, ValueError)` -> die Exception schlug bis zum aeusseren `except`
durch und setzte `state.programmer = {}` (Verlust-Amplifikation). Der Guard
faengt jetzt zusaetzlich `OverflowError`, sodass nur der eine kaputte Wert faellt.
"""
import os
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state
from src.core.show import show_file


def _write_lshow(path, show_json_text):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("show.json", show_json_text)


class ShowLoadOverflowGuardTest(unittest.TestCase):
    def _tmp_lshow(self, text):
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, "ovf.lshow")
        _write_lshow(p, text)
        return p

    def test_inf_value_skips_only_that_value_not_whole_programmer(self):
        # 1e999 (-> inf) neben guten Werten, sowohl im Programmer als auch in den
        # Base-Levels. RAW-JSON-Token 1e999, exakt wie es json.loads parst.
        text = (
            '{"version": "%s",'
            ' "programmer": {"1": {"intensity": 200, "dimmer": 1e999, "color_r": 50}},'
            ' "base_levels": {"2": {"intensity": 1e999, "dimmer": 80}}}'
            % show_file.SHOW_VERSION
        )
        path = self._tmp_lshow(text)
        ok, msg = show_file.load_show(path)
        self.assertTrue(ok, msg)

        st = get_state()
        # Ohne den Fix waere der GANZE Programmer {} — hier muessen die guten Werte
        # ueberleben und NUR der inf-Wert fehlen.
        self.assertIn(1, st.programmer)
        self.assertEqual(st.programmer[1].get("intensity"), 200)
        self.assertEqual(st.programmer[1].get("color_r"), 50)
        self.assertNotIn("dimmer", st.programmer[1])       # inf uebersprungen

        # Base-Levels analog: guter Wert bleibt, inf faellt (nicht alle geloescht).
        self.assertIn(2, st.base_levels)
        self.assertEqual(st.base_levels[2].get("dimmer"), 80)
        self.assertNotIn("intensity", st.base_levels[2])   # inf uebersprungen

    def test_negative_inf_also_guarded(self):
        # -1e999 -> -inf -> int() wirft ebenfalls OverflowError.
        text = (
            '{"version": "%s",'
            ' "programmer": {"3": {"intensity": -1e999, "dimmer": 120}}}'
            % show_file.SHOW_VERSION
        )
        path = self._tmp_lshow(text)
        ok, msg = show_file.load_show(path)
        self.assertTrue(ok, msg)
        st = get_state()
        self.assertIn(3, st.programmer)
        self.assertEqual(st.programmer[3].get("dimmer"), 120)
        self.assertNotIn("intensity", st.programmer[3])


if __name__ == "__main__":
    unittest.main()
