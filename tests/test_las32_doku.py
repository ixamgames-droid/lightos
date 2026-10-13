"""LAS-32 (S1): Anleitung und Changelog versprechen keinen Laserschutz.

Der Abschnitt „Sperrzonen (Vorschau)" beginnt mit den GRENZEN — bevor
irgendeine Bedienung erklaert wird.
"""
import pathlib
import unittest

from src.core.laser import sperrzonen as S

_REPO = pathlib.Path(__file__).resolve().parent.parent
_ANLEITUNG = _REPO / "docs" / "anleitung_laser" / "ANLEITUNG_LASER.md"


def _abschnitt() -> str:
    text = _ANLEITUNG.read_text(encoding="utf-8")
    start = text.index("## 9. Sperrzonen (Vorschau)")
    ende = text.index("### Siehe auch", start)
    return text[start:ende]


class DokuTest(unittest.TestCase):
    def test_grenzen_stehen_ganz_oben(self):
        a = _abschnitt()
        zeilen = [z for z in a.splitlines()[1:] if z.strip()]
        self.assertTrue(zeilen[0].startswith("> **Grenzen"), zeilen[0])
        grenzen = a.index("Grenzen")
        for spaeter in ("Zonen anlegen", "Maximalfeld je Laser", "Meldung je Laser"):
            self.assertLess(grenzen, a.index(spaeter), spaeter)

    def test_grenzen_nennen_blende_abstaende_laserschutzbeauftragten(self):
        kopf = _abschnitt().split("Wozu es trotzdem gut ist")[0]
        flach = " ".join(kopf.replace(">", " ").split())
        for wort in ("Nur Anzeige", "**nicht** ab", "Kein Ersatz", "Blende",
                     "Abstände", "Laserschutzbeauftragten", "Spiegelungen",
                     "noch nicht abgenommen"):
            self.assertIn(wort, flach, wort)

    def test_anleitung_nennt_die_meldungen_der_oberflaeche(self):
        flach = " ".join(_abschnitt().split())
        self.assertIn(S.HINWEIS_NUR_ANZEIGE, flach)
        for text in ("erreicht keine Zone", "Randwinkel fehlen — nicht prüfbar",
                     "Laser gepatcht, keine Sperrzonen angelegt"):
            self.assertIn(text, flach, text)
        self.assertIn(f"Vorgabe {S.ZUSCHLAG_STANDARD:g}°", flach)
        self.assertIn(f"mindestens {S.ZUSCHLAG_MIN:g}°", flach)

    def test_kein_schutzversprechen(self):
        texte = [_abschnitt(),
                 (_REPO / "changelog.d" / "2026-10-10-LAS-32.md").read_text(encoding="utf-8")
                 if (_REPO / "changelog.d" / "2026-10-10-LAS-32.md").exists() else ""]
        for t in texte:
            klein = t.lower()
            for wort in ("schützt", "geschützt", "abgesichert", "sicherheitsfunktion",
                         "verhindert"):
                self.assertNotIn(wort, klein, wort)
            self.assertNotIn("Freigabe erteilt", t)


if __name__ == "__main__":
    unittest.main()
