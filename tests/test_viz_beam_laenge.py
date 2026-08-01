"""VIZ-BEAM-OCCLUSION (Teil 1): der Lichtkegel endet am Boden.

Der sichtbare Strahl ist ein additiver Fake-Kegel mit FESTER Länge — er endete
deshalb nicht an der Fläche, die er trifft, sondern lief hindurch. Bei einem
tief stehenden oder steil nach unten gerichteten Scheinwerfer ragte damit ein
Stück Licht unter die Bühne.

Das ist der billige und zugleich auffälligste Teil der Verdeckung: eine
Skalierung, kein Ray-March. **Bewusst nur der Boden** — ein Raycast gegen alle
Bühnenobjekte je Fixture je Frame wäre im 44-Hz-Pfad genau die Sorte Kosten,
vor der die Review-Checkliste warnt. Der Bodenauftreffpunkt wird ohnehin schon
für den Lichtfleck gerechnet, diese Länge ist also gratis.

Geprüft wird die Rechen-Regel gegen die Quelle: dass der Kegel nie länger als
sein Grundmaß wird (sonst leuchtete ein hoch hängender Scheinwerfer plötzlich
30 m weit), nie auf 0 kollabiert (ein Kegel ohne Länge wäre ein unsichtbarer
Punkt statt eines kurzen Strahls) und beim Kürzen mitwandert (sonst schwebt er).

> **Einordnung seit VIZ-15 (2026-08-01):** diese Datei prüft *Quelltext*, und das
> ist die schwächere Testsorte — eine falsche Formel mit richtigen Zeichenketten
> käme hier durch. Die eigentliche **Rechnung** ist inzwischen als reine Funktion
> `beamLengthScale(base, dist, maxRange)` herausgezogen und wird in
> `tests/test_viz15_beam_range_scene.py` mit Zahlen gefahren (dort entscheidet
> sich, welche der drei Grenzen gewinnt). Was hier bleibt, sind die
> **Struktur**-Zusagen, die eine Zahlenrechnung nicht abdecken kann: dass es
> keinen zweiten Raycast gibt und dass die Position mit der Länge mitwandert.
"""
from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "ui", "visualizer", "scene_src", "fixtures", "builders.js")
_FIX = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "ui", "visualizer", "scene_src", "fixtures", "fixtures.js")


def _soll(dist, basis):
    """Die Regel aus setBeamLength, hier nachgebildet."""
    return max(0.15, min(basis, dist))


class RegelTest(unittest.TestCase):
    def test_nie_laenger_als_das_grundmass(self):
        self.assertEqual(_soll(30.0, 8.0), 8.0)

    def test_kuerzt_auf_den_auftreffpunkt(self):
        self.assertAlmostEqual(_soll(3.2, 8.0), 3.2)

    def test_kollabiert_nicht_auf_null(self):
        self.assertGreater(_soll(0.0, 8.0), 0.0)
        self.assertGreater(_soll(-5.0, 8.0), 0.0)


class QuelleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = open(_JS, encoding="utf-8").read()
        cls.fx = open(_FIX, encoding="utf-8").read()

    def test_grundlaenge_wird_gemerkt(self):
        """★ Ohne Referenz waere jede Anpassung kumulativ und der Kegel liefe
        nach ein paar Frames weg — dieselbe Falle wie beim Zoom-Winkel."""
        self.assertIn("baseBeamLength", self.fx)
        self.assertIn("f.baseBeamLength", self.js)

    def test_kegel_wandert_beim_kuerzen_mit(self):
        """Der Kegel haengt mit seiner MITTE unter der Linse. Wird er kuerzer,
        ohne dass die Position folgt, schwebt er frei in der Luft."""
        self.assertIn("beam.position.y = -(f.baseBeamLength * k) / 2", self.js)

    def test_kein_zappeln_bei_winzigen_aenderungen(self):
        """Der Wert kommt aus einer Pan/Tilt-Rechnung und schwankt minimal —
        ohne Totzone schriebe der 44-Hz-Pfad jeden Frame eine neue Skalierung."""
        self.assertIn("< 0.01) return", self.js)

    def test_nur_der_boden_nicht_beliebige_geometrie(self):
        """Die Beschraenkung ist eine Entscheidung, keine Luecke — sie steht im
        Kommentar, damit sie beim naechsten Anfassen nicht als Versehen gilt."""
        self.assertIn("BEWUSST NUR DER BODEN", self.js)

    def test_haengt_am_vorhandenen_auftreffpunkt(self):
        """Die Kegellaenge kommt aus dem Bodenpunkt, der in ``applyFloorAim``
        ohnehin gerechnet wird — NICHT aus einem zweiten, eigenen Raycast. Ein
        Strahl gegen alle Buehnenobjekte je Fixture je Frame ist im 44-Hz-Pfad
        genau die Kostenklasse, vor der die Review-Checkliste warnt.

        VIZ-15 hat den Aufruf aus dem innersten Zweig herausgezogen (er lief
        sonst NUR bei Bodentreffer, ein waagerechter Kopf bekam nie eine Laenge).
        Geprueft wird deshalb die Invariante statt der frueheren Zeile: der
        Abstand stammt aus dem vorhandenen ``t``, wird EINMAL angewandt, und es
        entsteht kein zusaetzlicher Strahl.
        """
        i = self.js.index("function applyFloorAim")
        block = self.js[i:i + 2800]
        self.assertIn("bodenAbstand = t", block,
                      "der Abstand muss aus dem schon gerechneten t kommen")
        self.assertIn("setBeamLength(f, bodenAbstand)", block)
        self.assertEqual(block.count("setBeamLength(f,"), 1,
                         "genau EINE Anwendung — zwei waeren zwei Wahrheiten")
        for teuer in ("Raycaster", "intersectObjects", "intersectObject("):
            self.assertNotIn(teuer, block,
                             f"{teuer} im 44-Hz-Pfad waere ein zweiter Strahl")


if __name__ == "__main__":
    unittest.main()
