"""CDX-70 (Codex zu #1255): DXF mit grossen Absolutkoordinaten verliert keine
feinen Details. Vorher landeten die Rohpunkte als float32 im Sammler, bevor
``_normieren`` zentrierte — eine 1-cm-Linie bei x = 500000 m hatte danach
keine Ausdehnung mehr und wurde abgelehnt."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.core.stage import modell_import as mi  # noqa: E402


def _dxf_linie(x1, y1, x2, y2) -> bytes:
    teile = [(0, "SECTION"), (2, "ENTITIES"),
             (0, "LINE"), (8, "0"), (10, x1), (20, y1), (30, 0), (11, x2), (21, y2), (31, 0),
             (0, "ENDSEC"), (0, "EOF")]
    return "".join(f"{c}\n{w}\n" for c, w in teile).encode("ascii")


class GrosseKoordinatenTest(unittest.TestCase):
    def _lies(self, daten):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "plan.dxf")
            with open(p, "wb") as f:
                f.write(daten)
            return mi.lies_datei(p, "m", True)

    def test_kurze_linie_weit_vom_ursprung_bleibt_erhalten(self):
        netz = self._lies(_dxf_linie(500000, 0, 500000.01, 0))
        self.assertEqual(netz.strecken, 1)
        self.assertAlmostEqual(netz.groesse[0], 0.01, places=4)

    def test_details_bleiben_nach_dem_zentrieren_unterscheidbar(self):
        # 2-mm-Versatz im Landeskoordinatensystem bleibt sichtbar
        netz = self._lies(_dxf_linie(3500000.000, 5500000.000, 3500000.002, 5500000.000))
        self.assertAlmostEqual(netz.groesse[0], 0.002, places=5)
        xs = sorted(netz.positionen[0::3])
        self.assertAlmostEqual(xs[-1] - xs[0], 0.002, places=5)

    def test_positionen_bleiben_float32(self):
        netz = self._lies(_dxf_linie(0, 0, 1, 0))
        self.assertEqual(netz.positionen.typecode, "f")


if __name__ == "__main__":
    unittest.main()
