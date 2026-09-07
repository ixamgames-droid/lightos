"""XPLAT-33: Die Pixel-Kopf-Szene wird EINMAL geladen, nicht je Test.

Warum das eine eigene Pruefung verdient: ``test_fm14_pixel_head_scene`` hat
25 Tests, und jeder hat sich frueher die volle Seite neu gebaut. Gemessen
(Sitzung B, 2026-09-07): Vollaufbau 7,1 s, reiner Fixture-Neubau 0,31 s —
in Summe 277 s gegen ein 300-s-Zeitlimit. Und unter einer Mutation, also
genau dann, wenn die Datei etwas zu melden HAT, stieg sie auf 313 s und lief
ins Limit. Ein Timeout macht das Gate laut XPLAT-28 nicht rot: die Datei
haette ihren eigenen Befund verschluckt.

Wer die Seite wieder je Test laedt, faellt in dieselbe Grube zurueck. Diese
Datei haelt die Vorbedingungen fest, die den Umbau tragen.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Das MODUL importieren, nicht die Klasse: ein ``from ... import
# PixelHeadSceneTest`` macht die fremde Testklasse zum Modul-Attribut hier —
# pytest sammelt ihre 25 Tests dann ein ZWEITES Mal ein (gemessen: 28 statt 3).
import test_fm14_pixel_head_scene as fm14        # noqa: E402

_FARBE = f"window.__fm14.seg({fm14._SPIIDER}, 2).material.color.g"


class SzeneEinmalLadenTest(unittest.TestCase):
    """Nutzt die echte Klasse als Werkzeug — sie ist der Gegenstand."""

    def setUp(self):
        self._tc = fm14.PixelHeadSceneTest("test_neunzehn_segmente_am_kopf_und_sonst_nichts")
        self._tc.setUp()

    def tearDown(self):
        # Klasse wieder unberuehrt hinterlassen: das echte Testfile baut sich
        # danach selbst neu auf (setUp legt die View an, wenn sie fehlt).
        fm14.PixelHeadSceneTest.tearDownClass()

    def test_zwei_aufbauten_laden_die_seite_nur_einmal(self):
        """★ Die Abnahme als Zahl. ``_geladen`` sammelt jedes loadFinished;
        nach zwei Aufbauten darf genau EINES drinstehen."""
        self._tc._aufbauen()
        self.assertEqual(len(fm14.PixelHeadSceneTest._geladen), 1,
                         "der erste Aufbau muss die Seite genau einmal laden")
        self._tc._aufbauen()
        self.assertEqual(len(fm14.PixelHeadSceneTest._geladen), 1,
                         "der zweite Aufbau darf die Seite NICHT neu laden")

    def test_der_neuaufbau_setzt_dmx_werte_zurueck(self):
        """★★ Die Vorbedingung fuer das Teilen: was ein Test faerbt, darf der
        naechste nicht vorfinden. Mit Positivkontrolle — ohne sie wuerde ein
        Batch, der gar nichts faerbt, hier als 'zurueckgesetzt' durchgehen."""
        self._tc._aufbauen()
        self.assertLess(float(self._tc._eval(_FARBE)), 0.9, "Startwert ist nicht dunkel")
        self.assertTrue(self._tc._dmx(fm14._ROT_MIT_GRUENEM_PIXEL, f"{_FARBE} > 0.9"),
                        "Positivkontrolle: der DMX-Batch hat gar nichts gefaerbt")
        self.assertGreater(float(self._tc._eval(_FARBE)), 0.9)
        self._tc._aufbauen()
        self.assertLess(float(self._tc._eval(_FARBE)), 0.9,
                        "der Neuaufbau laesst den Wert des Vortests stehen")

    def test_addfixture_ersetzt_das_objekt_und_nicht_nur_seine_felder(self):
        """Der Neuaufbau wird daran erkannt, dass eine Marke am Objekt
        verschwindet. Traegt ``addFixture`` seine Werte kuenftig ins ALTE
        Objekt ein, ueberlebt die Marke — dann wartet ``_aufbauen`` ins
        Zeitlimit statt falsch weiterzulaufen, und zwar hier zuerst."""
        self._tc._aufbauen()
        self._tc._eval(f"window.__lightos.fixtures['{fm14._GROSS}'].__marke = 1; true")
        self.assertTrue(self._tc._eval(f"!!window.__lightos.fixtures['{fm14._GROSS}'].__marke"),
                        "Positivkontrolle: die Marke liess sich gar nicht setzen")
        self._tc._aufbauen()
        self.assertFalse(self._tc._eval(f"!!window.__lightos.fixtures['{fm14._GROSS}'].__marke"),
                         "addFixture hat das Objekt nicht ersetzt")


if __name__ == "__main__":
    unittest.main()
