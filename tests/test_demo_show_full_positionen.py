"""DOC-17 (e): Demo_Show_Full — 2D-Bühne und 3D-Lage aus EINER Quelle.

Die 2D-Bühne ist seit dem Szenengraphen eine Projektion der 3D-Weltposition
(X/Z). ``tools/build_demo_show_full.py`` setzte frueher erst ein eigenes
2D-Layout (``live_view_positions``) und danach ``visualizer_positions`` — die
zweite Zuweisung ueberschrieb X/Z, das 2D-Layout war toter Code (gemessen:
PARs gewollt bei x=230..965 px / y=420, gespeichert x=207..391 px / y=200).
Der Generator setzt deshalb nur noch die 3D-Werte.
"""
import ast
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.show.show_file import load_show, reset_show
from src.core.stage.coords import world3d_to_live

_app = QApplication.instance() or QApplication([])

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(_ROOT, "tools", "build_demo_show_full.py")
SHOW = os.path.join(_ROOT, "shows", "Demo_Show_Full.lshow")


def _assigned_state_attrs(path: str) -> list[str]:
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    names = []
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else [])
        for t in targets:
            if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                    and t.value.id == "state"):
                names.append(t.attr)
    return names


def _assert_projection(tc: unittest.TestCase, lv: dict, vz: dict, fids) -> None:
    for fid in fids:
        exp = world3d_to_live(vz[fid][0], vz[fid][2])
        tc.assertAlmostEqual(float(lv[fid][0]), exp[0], places=2, msg=f"fid {fid} x")
        tc.assertAlmostEqual(float(lv[fid][1]), exp[1], places=2, msg=f"fid {fid} y")


class GeneratorSetztNurDreiD(unittest.TestCase):
    def test_kein_zweites_2d_layout(self):
        attrs = _assigned_state_attrs(GENERATOR)
        self.assertIn("visualizer_positions", attrs)
        self.assertNotIn(
            "live_view_positions", attrs,
            "build_demo_show_full.py weist live_view_positions zu — das wird von "
            "visualizer_positions ueberschrieben (2D = Projektion der 3D-Lage).")


class SpaetereDreiDZuweisungGewinnt(unittest.TestCase):
    """Belegt die Falle, gegen die der Generator-Waechter oben schuetzt."""

    def setUp(self):
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    def test_visualizer_positions_ueberschreibt_2d(self):
        st = self.state
        st.live_view_positions = {1: [230.0, 420.0], 2: [965.0, 420.0]}
        vz = {1: (-4.625, 0.0, 0.0), 2: (4.5625, 0.0, 0.0)}
        st.visualizer_positions = vz
        lv = dict(st.live_view_positions)
        _assert_projection(self, lv, vz, (1, 2))
        self.assertNotAlmostEqual(float(lv[1][1]), 420.0, places=1)


@unittest.skipUnless(os.path.exists(SHOW), "Demo_Show_Full.lshow nicht vorhanden")
class DemoShowFullLage(unittest.TestCase):
    def setUp(self):
        ok, msg = load_show(SHOW)
        self.assertTrue(ok, msg)
        self.state = get_state()

    def tearDown(self):
        reset_show()

    def test_2d_ist_projektion_und_reihenfolge_stimmt(self):
        lv = dict(self.state.live_view_positions)
        vz = dict(self.state.visualizer_positions)
        pars, mhs, spiders = list(range(1, 9)), [9, 10], [11, 12]
        _assert_projection(self, lv, vz, pars + mhs + spiders)
        xs = [float(lv[f][0]) for f in pars]
        self.assertEqual(xs, sorted(xs), "PAR-Reihe nicht links->rechts")
        # MH hinten (kleineres y), Spider vorne (groesseres y) als die PAR-Reihe.
        self.assertLess(float(lv[9][1]), float(lv[1][1]))
        self.assertGreater(float(lv[11][1]), float(lv[1][1]))


if __name__ == "__main__":
    unittest.main()
