"""VIZ-97: Gobo-Namen des Conti Moving Head bekommen ihr Motiv (3D + VC).

``gobo_icons._KEYWORDS`` kannte "Tunnel" und "3 Kreise" nicht (fuer "Kreise"
gab es nur "kreisen"/"kreis aus"). Folge: ``gobo_style_for`` lieferte "",
im 3D blieb der Strahl ohne Gobo-Motiv (der Nummern-Ausweg aus VIZ-83 greift
nur bei "Gobo N"), und die VC-Taste zeigte kein Symbol — auch nicht fuer die
"(Shake)"-Bereiche mit demselben Namen. Fund aus der Durchsicht der
Bierpong-Show.

Der Conti hat dasselbe China-Rad wie der ZQ02001 (``fixture_db``: "gleiches
China-Rad"), auf denselben DMX-Bereichen. Der Test verlangt deshalb: an jedem
Gobo-Wert zeigen beide Profile dasselbe Motiv.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                       # noqa: E402

_app = QApplication.instance() or QApplication([])

from src.core.database import fixture_db as FDB                  # noqa: E402
from src.ui.widgets.gobo_icons import (                          # noqa: E402
    STYLES, gobo_pixmap_for_name, gobo_style_for, is_shake_name)


class _Bereich:
    def __init__(self, von, bis, name):
        self.range_from, self.range_to, self.name = von, bis, name


class _Kanal:
    def __init__(self, liste):
        self.attribute = "gobo_wheel"
        self.ranges = [_Bereich(v, b, n) for v, b, n, _k in liste]


class ContiNamen(unittest.TestCase):

    def test_alle_conti_gobos_haben_ein_motiv(self):
        erwartet = {"Ring": "ring_slits", "Tunnel": "ovals",
                    "3 Kreise": "circle_of_circles", "Tetris": "tetris",
                    "Punkte": "dots", "Spirale": "spiral", "Zebra": "zebra"}
        for name, stil in erwartet.items():
            with self.subTest(name):
                self.assertEqual(gobo_style_for(name), stil)
            with self.subTest(name + " (Shake)"):
                self.assertEqual(gobo_style_for(name + " (Shake)"), stil)
                self.assertTrue(is_shake_name(name + " (Shake)"))

    def test_conti_und_zq_zeigen_am_selben_wert_dasselbe_motiv(self):
        zq = _Kanal(FDB._ZQ_MH_GOBO)
        conti = _Kanal(FDB._CONTI_GOBO)
        for wert in range(8, 64):            # statische Gobos 1..7
            zq_name = next(r.name for r in zq.ranges if r.range_from <= wert <= r.range_to)
            conti_name = next(r.name for r in conti.ranges if r.range_from <= wert <= r.range_to)
            with self.subTest(wert=wert, zq=zq_name, conti=conti_name):
                self.assertIn(gobo_style_for(zq_name), STYLES)
                self.assertEqual(gobo_style_for(conti_name), gobo_style_for(zq_name))

    def test_3d_bekommt_das_motiv_auch_im_shake_bereich(self):
        from src.ui.visualizer.visualizer_service import _gobo_style
        kanal = _Kanal(FDB._CONTI_GOBO)
        for wert, stil in ((20, "ovals"), (28, "circle_of_circles"),
                           (84, "ovals"), (92, "circle_of_circles"), (0, "open")):
            with self.subTest(wert=wert):
                self.assertEqual(_gobo_style({"gobo_wheel": wert}, [kanal]), stil)

    def test_vc_symbol_mit_muster_statt_neutraler_nummer(self):
        for name in ("Tunnel", "3 Kreise (Shake)"):
            with self.subTest(name):
                pm = gobo_pixmap_for_name(name, size=26)
                self.assertFalse(pm.isNull())
                self.assertTrue(gobo_style_for(name))   # VC-Taste verlangt ein Muster

    def test_keine_falschen_treffer(self):
        for name in ("Offen", "Gobo-Wechsel langsam → schnell", "Auto-Programm"):
            with self.subTest(name):
                self.assertNotIn(gobo_style_for(name), ("ovals", "circle_of_circles"))


if __name__ == "__main__":
    unittest.main()
