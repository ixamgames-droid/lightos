"""LAS-36: Die Anleitungen sagen dasselbe wie das Programm — der Laser-NOT-AUS
wird nur mit Rueckfrage am Knopf oben rechts geloest, kein Wert loest ihn.

Vorher widersprachen sie sich: „Erste Schritte“ versprach die Rueckfrage, die
Buehnen-Show- und die Geraete-Generator-Anleitung (wie der Laser-Tab) nannten
„Betriebsart/Shutter neu setzen“ als Weg zurueck (Befund S-01, QA-96).
Reiner Text-Waechter (kein Qt) — steht in tools/doku_gates.txt.
"""
import os
import re
import unittest

_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _lies(*teile):
    with open(os.path.join(_ROOT, *teile), encoding="utf-8") as f:
        return re.sub(r"\s+", " ", f.read())


class DokuNotAusLoesenTest(unittest.TestCase):

    def test_erste_schritte(self):
        t = _lies("docs", "anleitung_erste_schritte", "ANLEITUNG.md")
        self.assertIn("Gelöst wird er nur bewusst", t)
        self.assertIn("Rückfrage bestätigen", t)
        self.assertIn("werden Laser-Werte gemerkt, der Laser bleibt dunkel", t)
        self.assertIn("gibt er sofort wieder aus, was eingestellt ist", t)

    def test_erste_schritte_englisch(self):
        t = _lies("docs", "anleitung_erste_schritte", "ANLEITUNG.en.md")
        self.assertIn("Nothing else releases it", t)
        self.assertIn("the laser stays dark", t)

    def test_laser_anleitung(self):
        t = _lies("docs", "anleitung_laser", "ANLEITUNG_LASER.md")
        self.assertIn("**NOT-AUS lösen:** nur mit dem Knopf **LASER NOT-AUS** oben rechts", t)
        self.assertIn("werden Werte gemerkt, der Laser bleibt dunkel", t)
        self.assertIn("sofort wieder aus, was eingestellt ist", t)

    def test_kein_alter_weg_zurueck_in_den_anleitungen(self):
        alt = (
            "löst erst ein bewusst gesetzter Shutter-Wert",
            "erst ein neuer Klick auf eine Betriebsart",
            "Betriebsart oder Muster neu wählen",
        )
        for teile in (
            ("docs", "anleitung_erste_schritte", "ANLEITUNG.md"),
            ("docs", "anleitung_laser", "ANLEITUNG_LASER.md"),
            ("docs", "anleitung_buehnen_show", "ANLEITUNG_BUEHNEN_SHOW.md"),
            ("docs", "anleitung_buehnen_show", "ANLEITUNG.md"),
            ("docs", "anleitung_fixture_generator", "ANLEITUNG_FIXTURE_GENERATOR.md"),
            ("docs", "components", "views", "laser_view.md"),
        ):
            t = _lies(*teile)
            for satz in alt:
                with self.subTest(datei=teile[-2] + "/" + teile[-1], satz=satz):
                    self.assertNotIn(satz, t)

    def test_buehnen_show_und_generator_nennen_den_knopf(self):
        for teile in (
            ("docs", "anleitung_buehnen_show", "ANLEITUNG_BUEHNEN_SHOW.md"),
            ("docs", "anleitung_fixture_generator", "ANLEITUNG_FIXTURE_GENERATOR.md"),
        ):
            t = _lies(*teile)
            with self.subTest(datei=teile[-1]):
                self.assertIn("**LASER NOT-AUS** oben rechts im Hauptfenster", t)
                self.assertIn("Rückfrage bestätigen", t)

    def test_laser_tab_nennt_den_alten_weg_nicht_mehr(self):
        """Der Wortlaut im Programm selbst (ohne die Ansicht zu bauen)."""
        with open(os.path.join(_ROOT, "src", "ui", "views", "laser_view.py"),
                  encoding="utf-8") as f:
            quelle = f.read()
        self.assertNotIn("neu wählen", quelle)
        self.assertNotIn("neu gewählt wird", quelle)
        self.assertIn("Lösen: Knopf oben rechts.", quelle)


if __name__ == "__main__":
    unittest.main()
