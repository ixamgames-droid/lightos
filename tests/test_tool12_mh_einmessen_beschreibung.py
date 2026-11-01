"""TOOL-12: ``tools/mh_einmessen.py`` beschreibt nur noch, was es kann.

**Der Befund.** Der Docstring (er ist zugleich der Hilfetext und wird beim Start
als Bedienhilfe ausgegeben) versprach eine Taste ``m`` ("Zielpunkt vermessen"),
einen "fertigen Python-Schnipsel" als Ausgabe und eine Erkennung vertauschter
Koepfe. Nichts davon gibt es im Code. Wer das Werkzeug am Rig nach der
Beschreibung bedient, drueckt ``m`` und es passiert nichts.

Jetzt: ehrliche Grenzen, Hinweis "veraltet" auf das Einmessen in der App
(VIZ-55, docs/anleitung_einmessen) in Hilfetext und Startmeldung.

Das Werkzeug wird hier NICHT ausgefuehrt (es oeffnet echte Hardware) — nur
geladen, wie in ``tests/test_viz60_einmessen.py``; ``--help`` beendet vor jedem
Port-Zugriff.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import re
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PFAD = os.path.join(_ROOT, "tools", "mh_einmessen.py")
_ANLEITUNG = os.path.join(_ROOT, "docs", "anleitung_einmessen",
                          "ANLEITUNG_EINMESSEN.md")


def _modul():
    spec = importlib.util.spec_from_file_location("mh_einmessen_tool12", _PFAD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BeschreibungIstEhrlichTest(unittest.TestCase):
    def setUp(self):
        self.m = _modul()
        self.doc = self.m.__doc__
        with open(_PFAD, encoding="utf-8") as f:
            self.quelle = f.read()

    def test_keine_taste_m_versprochen(self):
        bedienung = self.doc.split("WIE ES BEDIENT WIRD")[1].split("WAS DIESES")[0]
        self.assertIsNone(re.search(r"^\s+m\s{2,}", bedienung, re.M),
                          "Bedienhilfe nennt eine Taste 'm', die es nicht gibt")
        # Gegenprobe: die Hauptschleife kennt wirklich keine Taste 'm'.
        self.assertNotIn('t == "m"', self.quelle)
        self.assertNotIn("tl == \"m\"", self.quelle)

    def test_kein_python_schnipsel_versprochen(self):
        self.assertNotIn("Schnipsel", self.doc)

    def test_keine_vertauscht_erkennung_versprochen(self):
        self.assertNotIn("Die Rueckrechnung erkennt es", self.doc)

    def test_grenzen_stehen_drin(self):
        for wort in ("zwei Koepfe", "Enttec", "Hero Spot 90",
                     "Pan-Bereich wird NICHT ermittelt",
                     "LIGHTOS_ECHTE_AUSGABE=1"):
            self.assertIn(wort, self.doc)

    def test_veraltet_mit_verweis_auf_die_app(self):
        self.assertIn("VERALTET", self.doc.splitlines()[0])
        self.assertIn("VIZ-55", self.doc)
        self.assertIn("docs/anleitung_einmessen/ANLEITUNG_EINMESSEN.md", self.doc)
        self.assertTrue(os.path.isfile(_ANLEITUNG), "Verweis zeigt ins Leere")
        self.assertIn("VIZ-55", self.m.VERALTET_HINWEIS)

    def test_hilfetext_nennt_veraltet(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            self.m.main(["--help"])
        text = " ".join(out.getvalue().split())
        self.assertIn("VERALTET", text)
        self.assertIn("Einmessen in der App", text)

    def test_laufzeitmeldungen_versprechen_keine_auswertung(self):
        # Auch die Konsolenmeldungen versprachen eine Pan-Bereich-Auswertung
        # ("dann entscheidet die Rechnung selbst", "Auswertung: siehe
        # Zusammenfassung"), die die Zusammenfassung nie liefert.
        self.assertNotIn("entscheidet die Rechnung selbst", self.quelle)
        self.assertNotIn("Auswertung: siehe Zusammenfassung", self.quelle)
        self.assertNotIn("der Pan-Bereich ist damit bestimmbar.", self.quelle)
        # Ausgefuehrt: die Mehrdeutigkeits-Meldung sagt ehrlich, dass nichts
        # ausgewertet wird (reine Rechnung, keine Hardware).
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.zeige_zweideutigkeit(10.0, 2.5)
        self.assertIn("wertet das nicht aus", " ".join(out.getvalue().split()))

    def test_startmeldung_nennt_veraltet(self):
        # Steht vor der Port-Pruefung in main(), nicht nur im Hilfetext.
        haupt = self.quelle.split("def main(")[1]
        self.assertLess(haupt.index("print(VERALTET_HINWEIS)"),
                        haupt.index("port_halter("))


if __name__ == "__main__":
    unittest.main()
