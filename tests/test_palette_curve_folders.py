"""FLD-01c: Paletten und Kurven bekommen einen (verschachtelten) Ordnerpfad.

Reine Modell-/Persistenz-Tests (folder wird serialisiert + rückwärtskompatibel).
"""
import unittest

from src.core.engine.palette import Palette, PaletteType, PaletteManager
from src.core.engine.fade_curve import FadeCurve
from src.core.engine.curve_library import CurveLibrary


class PaletteFolderTest(unittest.TestCase):
    def test_round_trip(self):
        p = Palette(name="Warm", type=PaletteType.COLOR,
                    values={"color_r": 255}, folder="Stimmung/Warm")
        p2 = Palette.from_dict(p.to_dict())
        self.assertEqual(p2.folder, "Stimmung/Warm")

    def test_backward_compat(self):
        p = Palette.from_dict({"name": "X", "type": "Color", "values": {}})
        self.assertEqual(p.folder, "")

    def test_manager_round_trip(self):
        m = PaletteManager()
        m.add(Palette(name="Tief", type=PaletteType.COLOR,
                      values={"color_b": 255}, folder="Blau"))
        m2 = PaletteManager()
        m2.from_dict(m.to_dict())
        found = [p for p in m2.get_by_type(PaletteType.COLOR) if p.name == "Tief"]
        self.assertTrue(found)
        self.assertEqual(found[0].folder, "Blau")


class CurveFolderTest(unittest.TestCase):
    def test_round_trip(self):
        c = FadeCurve(name="Soft", mode="smooth", folder="Fades/Soft")
        c2 = FadeCurve.from_dict(c.to_dict())
        self.assertEqual(c2.folder, "Fades/Soft")

    def test_copy_keeps_folder(self):
        c = FadeCurve(name="Soft", folder="Fades")
        self.assertEqual(c.copy().folder, "Fades")

    def test_backward_compat(self):
        c = FadeCurve.from_dict({"name": "X", "points": [[0, 0], [1, 1]]})
        self.assertEqual(c.folder, "")

    def test_library_round_trip(self):
        lib = CurveLibrary()
        lib.add(FadeCurve(name="MyFade", folder="Custom"))
        lib2 = CurveLibrary()
        lib2.from_dict(lib.to_dict())
        found = [c for c in lib2.user_curves() if c.name == "MyFade"]
        self.assertTrue(found)
        self.assertEqual(found[0].folder, "Custom")


if __name__ == "__main__":
    unittest.main()
