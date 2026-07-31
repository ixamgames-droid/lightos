"""VIZ-GOBO-3D: das Gobo-Muster erscheint im Bodenfleck (David-Wunsch 2026-07-16).

Der 3D-Viewer projizierte KEINE Gobos — `gobo`/`gobo_wheel` kam im gesamten
Renderer nicht vor. Ein Gobo-Wechsel (etwa der MH-Gobo-Chaser der Demoshows)
hatte damit null sichtbare Wirkung, obwohl das Rad im Programmer läuft.

Zwei Entscheidungen, die der Test festhält:

1. **Nach JS wandert der erkannte MUSTER-STIL, nicht der DMX-Wert.** Die
   Zuordnung Wert → Range-Name → Muster ist datengetrieben und lebt schon in
   `gobo_icons` (dieselbe Quelle wie die 2D-Kacheln im Programmer). Ginge der
   Rohwert rüber, müsste JS die Ranges des Profils kennen — eine zweite Quelle
   für dieselbe Zuordnung.
2. **Ein Gerät ohne Gobo-Rad bekommt keinen Schlüssel.** Wie bei Zoom/Iris:
   fehlend heißt „nichts anfassen", nicht „Vorgabewert".
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.ui.visualizer.visualizer_service import (      # noqa: E402
    _build_fixture_payload, _gobo_style,
)

_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "ui", "visualizer", "scene_src", "fixtures", "gobo_textures.js")


class _Range:
    def __init__(self, lo, hi, name):
        self.range_from, self.range_to, self.name = lo, hi, name
        self.kind = ""


class _Ch:
    def __init__(self, attribute, ranges=()):
        self.attribute = attribute
        self.ranges = list(ranges)


class _Fx:
    fid = 1
    fixture_type = "moving_head"


_GOBO_CH = _Ch("gobo_wheel", [
    _Range(0, 9, "Kein Gobo (offen)"),
    _Range(10, 19, "Gobo 1 (Ring mit Spalten)"),
    _Range(20, 29, "Gobo 2 (Ovale)"),
    _Range(30, 39, "Gobo 6 (Spirale)"),
    _Range(40, 49, "Gobo 9 (unbekanntes Muster)"),
])


class StilErkennungTest(unittest.TestCase):
    def test_muster_kommt_aus_dem_range_namen(self):
        self.assertEqual(_gobo_style({"gobo_wheel": 15}, [_GOBO_CH]), "ring_slits")
        self.assertEqual(_gobo_style({"gobo_wheel": 25}, [_GOBO_CH]), "ovals")
        self.assertEqual(_gobo_style({"gobo_wheel": 35}, [_GOBO_CH]), "spiral")

    def test_offen_ist_leerer_stil_nicht_none(self):
        """Wichtiger Unterschied: „" heisst „Rad steht auf offen" (Fleck ohne
        Muster), ``None`` heisst „Geraet hat gar kein Rad"."""
        self.assertEqual(_gobo_style({"gobo_wheel": 5}, [_GOBO_CH]), "open")

    def test_unbekannter_name_wird_nicht_geraten(self):
        self.assertEqual(_gobo_style({"gobo_wheel": 45}, [_GOBO_CH]), "")

    def test_geraet_ohne_gobo_rad_liefert_none(self):
        self.assertIsNone(_gobo_style({"intensity": 255}, [_Ch("intensity")]))

    def test_ohne_kanalliste_keine_behauptung(self):
        self.assertIsNone(_gobo_style({"gobo_wheel": 15}, None))


class PayloadTest(unittest.TestCase):
    def test_gobo_landet_im_payload(self):
        p = _build_fixture_payload(_Fx(), {"intensity": 255, "gobo_wheel": 35},
                                   [_GOBO_CH])
        self.assertEqual(p["gobo"], "spiral")

    def test_ohne_rad_kein_schluessel(self):
        p = _build_fixture_payload(_Fx(), {"intensity": 255}, [_Ch("intensity")])
        self.assertNotIn("gobo", p)


class JsSeiteTest(unittest.TestCase):
    """Die JS-Seite zeichnet die Muster — hier gegen die Quelle geprueft, damit
    ein umbenannter Stil nicht still im schwarzen Fleck endet."""

    @classmethod
    def setUpClass(cls):
        cls.js = open(_JS, encoding="utf-8").read()

    def test_alle_stile_aus_gobo_icons_werden_gezeichnet(self):
        from src.ui.widgets.gobo_icons import STYLES
        for stil in STYLES:
            self.assertIn(f"'{stil}'", self.js,
                          f"Stil {stil} hat JS-seitig kein Muster — der "
                          f"Bodenfleck bliebe schwarz")

    def test_unbekannter_stil_gibt_keine_textur(self):
        """„open"/unbekannt -> voller Fleck ohne Muster, nicht schwarz."""
        self.assertIn("return null;", self.js)

    def test_kein_spotlight_map(self):
        """three r128 kennt SpotLight.map nicht — der Weg ueber den Bodenfleck
        ist bewusst gewaehlt, nicht aus Bequemlichkeit."""
        self.assertNotIn(".map = goboTexture", self.js.replace(
            "spot.material.map = goboTexture", ""))

    def test_texturen_werden_gecacht(self):
        self.assertIn("CACHE", self.js)

    def test_unveraendertes_gobo_baut_kein_material_neu(self):
        """`needsUpdate` erzwingt einen Shader-Neubau — bei 44 Hz waere das
        teuer. Deshalb nur bei echter Aenderung."""
        self.assertIn("dmx.gobo === f.lastGobo", self.js)


if __name__ == "__main__":
    unittest.main()
