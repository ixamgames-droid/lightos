"""CDX-71 (Codex zu #1258): DXF mit Waenden + vorgeschlagenes Verkleinern.

Die Wandhoehe blieb beim Verkleinern fest (wand_hoehe_m / faktor), der
vorgeschlagene Massstab passte deshalb nicht: Linie Z 0..40 m + 3 m Waende
= 43 m hoch, nach dem Vorschlag noch 30,9 m > 30 m -> erneut abgelehnt."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.core.stage import modell_import as mi  # noqa: E402


def _dxf_schraege_linie() -> bytes:
    teile = [(0, "SECTION"), (2, "ENTITIES"),
             (0, "LINE"), (8, "0"), (10, 0), (20, 0), (30, 0), (11, 10), (21, 0), (31, 40),
             (0, "ENDSEC"), (0, "EOF")]
    return "".join(f"{c}\n{w}\n" for c, w in teile).encode("ascii")


class WandMassstabTest(unittest.TestCase):
    def test_vorgeschlagener_massstab_passt_auch_mit_waenden(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "halle.dxf")
            with open(p, "wb") as f:
                f.write(_dxf_schraege_linie())
            with self.assertRaises(mi.ModellZuGross) as cm:
                mi.lies_datei(p, "m", True, wand_hoehe_m=3.0)
            e = cm.exception
            self.assertAlmostEqual(e.groesse[1], 43.0, places=3)
            netz = mi.lies_datei(p, "m", True, wand_hoehe_m=3.0, massstab=e.passend)
            self.assertLessEqual(netz.groesse[1], mi.MAX_HOEHE_M)
            # gleichmaessig verkleinert: Hoehe = 43 m * Massstab
            self.assertAlmostEqual(netz.groesse[1], 43.0 * e.passend, places=3)

    def test_ohne_verkleinern_bleibt_die_wandhoehe_wie_eingegeben(self):
        teile = [(0, "SECTION"), (2, "ENTITIES"),
                 (0, "LINE"), (8, "0"), (10, 0), (20, 0), (30, 0), (11, 10), (21, 0), (31, 0),
                 (0, "ENDSEC"), (0, "EOF")]
        daten = "".join(f"{c}\n{w}\n" for c, w in teile).encode("ascii")
        netz = mi.lies_bytes(daten, ".dxf", "m", True, wand_hoehe_m=3.0)
        self.assertAlmostEqual(netz.groesse[1], 3.0, places=4)


if __name__ == "__main__":
    unittest.main()
