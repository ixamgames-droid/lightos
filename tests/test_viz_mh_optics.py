"""VIZ-MH-OPTICS: der 3D-Strahl folgt Zoom und Iris (David-Wunsch 2026-07-16).

Vorher war der Lichtkegel ein FESTER Winkel. Die Optik-Attribute waren im
Programmer längst steuerbar, kamen aber nie im 3D an — `zoom`/`iris` tauchten
im Renderer nirgends auf. Ein Zoom-Zug hatte damit null Wirkung, und man sah im
Visualizer etwas anderes als am echten Gerät.

Zwei Hälften, beide hier geprüft:

1. **Der Datenpfad.** Der Service schickte die Attribute gar nicht mit. Er tut
   es jetzt — aber NUR, wenn das Gerät sie wirklich hat: ein erfundener
   128er-Default würde jeden Scheinwerfer ohne Zoom auf halbe Weite stellen.
2. **Die Abbildung.** DMX 0..255 -> Skalierungsfaktor des Kegel-Radius.

Die Konvention (0 = eng, 255 = weit) ist eine Annahme — DMX sagt sie nicht.
Sie steht im Modul-Kopf, und eine Umkehr-Angabe pro Profil ist als eigener
Punkt notiert, statt sie hier zu raten.
"""
from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.ui.visualizer.visualizer_service import _build_fixture_payload  # noqa: E402

_OPTICS_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "ui", "visualizer", "scene_src", "fixtures", "optics.js")


class _Fx:
    fid = 1
    fixture_type = "moving_head"


class DatenpfadTest(unittest.TestCase):
    """Der Service muss die Optik-Attribute ueberhaupt erst mitschicken."""

    def test_zoom_und_iris_kommen_im_payload_an(self):
        p = _build_fixture_payload(_Fx(), {"intensity": 255, "zoom": 200, "iris": 40})
        self.assertEqual(p["zoom"], 200)
        self.assertEqual(p["iris"], 40)

    def test_fokus_und_frost_kommen_ebenfalls_an(self):
        """Kantenschaerfe (PR #534): ohne den Datenpfad bleibt die schoenste
        Kennlinie wirkungslos — genau daran scheiterte Zoom vor PR #523."""
        p = _build_fixture_payload(_Fx(), {"intensity": 255, "focus": 200, "frost": 90})
        self.assertEqual(p["focus"], 200)
        self.assertEqual(p["frost"], 90)

    def test_geraet_ohne_optik_bekommt_keine_erfundenen_werte(self):
        """★ Ein 128er-Default waere schlimmer als gar nichts: er stellte JEDEN
        Scheinwerfer ohne Zoom-Kanal auf halbe Weite. Fehlender Schluessel
        heisst JS-seitig „unveraendert"."""
        p = _build_fixture_payload(_Fx(), {"intensity": 255})
        for k in ("zoom", "iris", "focus", "frost"):
            self.assertNotIn(k, p)

    def test_bestandsfelder_unveraendert(self):
        p = _build_fixture_payload(_Fx(), {"intensity": 255, "pan": 10, "tilt": 20})
        for k in ("fid", "r", "g", "b", "intensity", "pan", "tilt"):
            self.assertIn(k, p)


class AbbildungTest(unittest.TestCase):
    """Die Kennlinie aus optics.js — gegen die Quelle geprueft, damit eine
    stille Aenderung der Konstanten hier auffaellt."""

    @classmethod
    def setUpClass(cls):
        cls.js = open(_OPTICS_JS, encoding="utf-8").read()

    def _konst(self, name):
        m = re.search(rf"const {name} = ([0-9.]+);", self.js)
        self.assertIsNotNone(m, f"{name} fehlt in optics.js")
        return float(m.group(1))

    def test_zoom_geht_von_eng_nach_weit(self):
        eng, weit = self._konst("ZOOM_ENG"), self._konst("ZOOM_WEIT")
        self.assertLess(eng, 1.0, "DMX 0 muss ENGER als der Grundwinkel sein")
        self.assertGreater(weit, 1.0, "DMX 255 muss WEITER sein")

    def test_iris_kann_nur_verengen(self):
        zu = self._konst("IRIS_ZU")
        self.assertGreater(zu, 0.0, "eine ganz geschlossene Iris darf den Kegel "
                                    "nicht auf 0 setzen — dann waere er weg statt schmal")
        self.assertLess(zu, 1.0, "eine geschlossene Iris muss verengen")

    def test_skalierung_wird_multiplikativ_kombiniert(self):
        """Zoom UND Iris zusammen: die Iris verengt, was der Zoom aufmacht.
        Additiv waere falsch — eine geschlossene Iris koennte einen weiten Zoom
        sonst nicht mehr einfangen."""
        self.assertIn("k *=", self.js)
        self.assertNotIn("k +=", self.js)

    def test_fehlender_wert_laesst_den_kegel_in_ruhe(self):
        """Der Service schickt DIFFERENTIELL — ein Batch ohne `zoom` heisst
        „unveraendert" und darf den Kegel nicht zurueckspringen lassen."""
        self.assertIn("f.lastZoom", self.js)
        self.assertIn("dmx.zoom !== undefined", self.js)

    def test_spot_skaliert_relativ_zum_grundwinkel(self):
        """★ Ohne gemerkten Grundwinkel waere jede Zoom-Aenderung kumulativ und
        der Kegel liefe nach ein paar Zuegen weg."""
        self.assertIn("baseSpotAngle", self.js)
        self.assertIn("Math.min(Math.PI / 2", self.js,
                      "ein SpotLight-Winkel >= PI/2 ist ungueltig")

    def test_konvention_ist_dokumentiert_nicht_stillschweigend(self):
        self.assertIn("EHRLICH ZUR KONVENTION", self.js)


if __name__ == "__main__":
    unittest.main()
