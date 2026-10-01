"""DOC-14: der VC-Widget-Schaukasten legt ALLE Widget-Typen ab, nicht 17 von 19.

``tools/build_vc_widgets_showcase.py`` legte 17 Typen ab und meldete selbst
„alle 17 Typen vorhanden" — die Canvas kennt aber 19 (``WIDGET_REGISTRY``). Es
fehlten ``VCTempoBusController`` und ``VCMultiLiveEditor``. Die Selbstpruefung
konnte das nicht sehen, weil sie gegen eine EIGENE Liste zaehlte.

Jetzt zaehlt sie gegen die Registry. Dieser Test haelt zweierlei fest:

* der Generator selbst (im Unterprozess, Ausgabe umgelenkt) legt jeden Typ der
  Registry ab und bleibt in der Aufnahmeflaeche (logisch 900 hoch);
* die eingecheckte ``geometry.json`` — sie steuert den Zuschnitt — kennt jeden
  Typ, und die 17 bisherigen Rechtecke sind unveraendert geblieben (die
  vorhandenen Bild-Ausschnitte stimmen weiter).

Das Uebersichtsbild selbst ist noch die alte Aufnahme; die Bildunterschrift
sagt das, bis es neu aufgenommen ist.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_vc_widgets_showcase.py")
GEO = os.path.join(REPO, "docs", "anleitung_vc_widgets", "_capture", "geometry.json")
AUFNAHME_HOEHE = 900        # logisch, s. _MAX_X/Kommentar im Generator

#: Die 17 Rechtecke vor DOC-14 — sie duerfen sich nicht verschieben, sonst
#: passen die vorhandenen Ausschnitte nicht mehr zu ihrem Widget.
_BISHER = {
    "VCButton": (30, 54, 160, 88), "VCSlider": (214, 54, 150, 184),
    "VCColor": (388, 54, 150, 114), "VCEncoder": (562, 54, 150, 144),
    "VCStepper": (736, 54, 150, 104), "VCSpeedDial": (910, 54, 160, 214),
    "VCXYPad": (1094, 54, 160, 184), "VCCueList": (1278, 54, 210, 184),
    "VCColorList": (30, 288, 230, 104), "VCEffectColors": (284, 288, 230, 110),
    "VCBpmDisplay": (538, 288, 190, 120), "VCBusSelector": (752, 288, 210, 110),
    "VCSongInfo": (986, 288, 220, 120), "VCLabel": (1230, 288, 220, 68),
    "VCEffectDisplay": (30, 428, 210, 148), "VCFrame": (264, 428, 240, 174),
    "VCEffectEditor": (528, 428, 380, 248),
}


def _registry():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
    return set(WIDGET_REGISTRY)


class EingecheckteGeometrie(unittest.TestCase):

    def setUp(self):
        with open(GEO, encoding="utf-8") as f:
            self.geo = json.load(f)["widgets"]

    def test_kennt_jeden_typ_der_registry(self):
        reg = _registry()
        self.assertGreaterEqual(len(reg), 19, "Registry auffaellig klein")
        self.assertEqual(sorted(reg - set(self.geo)), [],
                         "Widget-Typ ohne Platz im Schaukasten")

    def test_bisherige_rechtecke_unveraendert(self):
        for name, (x, y, w, h) in _BISHER.items():
            with self.subTest(widget=name):
                g = self.geo[name]
                self.assertEqual((g["x"], g["y"], g["w"], g["h"]), (x, y, w, h))

    def test_alles_in_der_aufnahmeflaeche(self):
        unten = {n: g["y"] + g["h"] for n, g in self.geo.items()}
        self.assertLessEqual(max(unten.values()), AUFNAHME_HOEHE, unten)


class GeneratorLegtAlleTypenAb(unittest.TestCase):

    def test_generator_meldet_alle_typen_der_registry(self):
        reg = _registry()
        with tempfile.TemporaryDirectory(prefix="lightos_doc14_") as tmp:
            show = os.path.join(tmp, "VC_Widgets_Showcase.lshow")
            geo = os.path.join(tmp, "geometry.json")
            env = dict(os.environ)
            env.update({"LIGHTOS_GEN_OUT": show, "LIGHTOS_GEN_GEO": geo,
                        "LIGHTOS_SHOW_DB": os.path.join(tmp, "show.db"),
                        "QT_QPA_PLATFORM": "offscreen", "PYTHONIOENCODING": "utf-8"})
            lauf = subprocess.run([sys.executable, GENERATOR], cwd=REPO, env=env,
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=300)
            ausgabe = lauf.stdout + lauf.stderr
            self.assertEqual(lauf.returncode, 0, ausgabe[-3000:])
            self.assertIn(f"alle {len(reg)} Typen vorhanden", lauf.stdout)
            with open(geo, encoding="utf-8") as f:
                erzeugt = json.load(f)
            with open(GEO, encoding="utf-8") as f:
                eingecheckt = json.load(f)
            self.assertEqual(erzeugt, eingecheckt,
                             "geometry.json ist nicht der Stand des Generators — "
                             "Generator laufen lassen und die Datei mit einchecken")


if __name__ == "__main__":
    unittest.main()
