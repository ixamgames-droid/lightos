"""LAS-25 / Codex-Review #959: die Doku beschreibt, was Blackout, Ziel-Blackout
und NOT-AUS an einen Laser senden.

Seit LAS-25 bekommen Laser dort den Aus-Wert aus dem Geraeteprofil, und der
ist nicht immer 0 (bei manchen Lasern heisst DMX 0 „Auto“). „Erste Schritte“
sagte weiter „alle Kanaele gehen auf 0 … Laser gehen komplett aus“, die
Laser-Anleitung nannte die Aus-Werte nur beim Grand Master — sicherheits-
relevant, weil der DMX-Monitor nach einem Blackout bei Lasern nicht ueberall
0 zeigt und ein Laser ohne Aus-Wert im Profil weiterstrahlen kann.
"""
import os
import unittest

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def _lies(*teile):
    with open(os.path.join(DOCS, *teile), encoding="utf-8") as fh:
        return fh.read()


class LaserAusWerteDokuTest(unittest.TestCase):
    def test_erste_schritte_verspricht_keine_null_fuer_laser(self):
        text = _lies("anleitung_erste_schritte", "ANLEITUNG.md")
        abschnitt = text[text.index("**BLACKOUT**"):][:1500]
        self.assertNotIn("Laser und Nebelmaschinen gehen", abschnitt)
        self.assertIn("Aus-Wert", abschnitt)
        self.assertIn("NOT-AUS", abschnitt)

    def test_laser_anleitung_beschreibt_blackout_und_not_aus(self):
        text = _lies("anleitung_laser", "ANLEITUNG_LASER.md")
        self.assertIn("### Blackout, Ziel-Blackout und NOT-AUS", text)
        abschnitt = text[text.index("### Blackout, Ziel-Blackout und NOT-AUS"):][:2000]
        for wort in ("BLACKOUT", "Ziel", "NOT-AUS", "nicht immer 0", "keinen"):
            self.assertIn(wort, abschnitt)


if __name__ == "__main__":
    unittest.main()
