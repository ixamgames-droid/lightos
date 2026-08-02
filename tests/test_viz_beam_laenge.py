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

    def test_die_beschraenkung_auf_den_boden_ist_aufgehoben(self):
        """Bis 2026-08-02 galt hier ausdruecklich „BEWUSST NUR DER BODEN".

        Das war eine KOSTEN-Entscheidung, keine gestalterische: ein Raycast je
        Fixture und Frame waere im 44-Hz-Pfad zu teuer. Aufgehoben wurde sie
        deshalb auch nicht durch Wegsehen, sondern durch eine Bremse — gerechnet
        wird nur bei Aenderung an Strahl oder Buehne (VIZ-BEAM-OCCLUSION Teil 2,
        Zusagen in `test_viz_beam_stop.py`). Der alte Kommentar darf nicht mehr
        dastehen, sonst liest ihn der naechste als geltende Regel.
        """
        self.assertNotIn("BEWUSST NUR DER BODEN", self.js,
                         "veralteter Kommentar: der Strahl endet jetzt auch an "
                         "Buehnenkoerpern")

    def test_haengt_am_vorhandenen_auftreffpunkt(self):
        """Die Kegellaenge kommt aus dem Auftreffpunkt, der in ``applyFloorAim``
        ohnehin gerechnet wird, und wird GENAU EINMAL angewandt.

        VIZ-15 hat den Aufruf aus dem innersten Zweig herausgezogen (er lief
        sonst NUR bei Bodentreffer, ein waagerechter Kopf bekam nie eine Laenge).

        **Geaendert am 2026-08-02:** frueher stand hier zusaetzlich „kein
        Raycaster in diesem Block". Seit Teil 2 gibt es einen — fuer die
        Buehnenkoerper, ohne die der Kegel durch jedes Podest schiesst. Die
        Kosten-Zusage ist damit nicht gefallen, sondern umgezogen: sie lautet
        jetzt „kein Strahl, solange sich nichts bewegt" und wird in
        `test_viz_beam_stop.py::test_kein_strahl_solange_sich_nichts_bewegt`
        geprueft. Was hier bleibt, ist die Struktur: EIN Auftreffpunkt, EINE
        Anwendung.
        """
        i = self.js.index("function applyFloorAim")
        block = self.js[i:i + 3400]
        self.assertIn("auftreffAbstand = t", block,
                      "der Abstand muss aus dem schon gerechneten t kommen")
        self.assertIn("setBeamLength(f, auftreffAbstand)", block)
        self.assertEqual(block.count("setBeamLength(f,"), 1,
                         "genau EINE Anwendung — zwei waeren zwei Wahrheiten")
        self.assertEqual(block.count("koerperTreffer(f,"), 1,
                         "genau EINE Koerper-Abfrage je Durchlauf")
