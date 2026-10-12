"""LAS-35: Die Anleitung beschreibt den Planer und den Einmess-Assistenten —
mit den Worten der Oberflaeche, den Grenzen ganz oben und ohne
Schutzversprechen."""
import pathlib
import re
import unittest

from src.core.laser import feld_einmessen as E
from src.core.laser import sperrzonen as S

_REPO = pathlib.Path(__file__).resolve().parent.parent
_ANLEITUNG = _REPO / "docs" / "anleitung_laser" / "ANLEITUNG_LASER.md"
_FRAGMENT = _REPO / "changelog.d" / "2026-10-11-LAS-35.md"


def _abschnitt() -> str:
    text = _ANLEITUNG.read_text(encoding="utf-8")
    start = text.index("## 9. Sperrzonen (Vorschau)")
    return text[start:text.index("### Siehe auch", start)]


def _flach(text: str) -> str:
    return " ".join(text.replace(">", " ").split())


class DokuTest(unittest.TestCase):
    def test_grenzen_stehen_vor_planer_und_assistent(self):
        a = _abschnitt()
        zeilen = [z for z in a.splitlines()[1:] if z.strip()]
        self.assertTrue(zeilen[0].startswith("> **Grenzen"), zeilen[0])
        grenzen = a.index("Grenzen")
        for spaeter in ("Der Planer", "Zonen anlegen und ziehen", "Feld einmessen —"):
            self.assertLess(grenzen, a.index(spaeter), spaeter)
        kopf = _flach(a.split("Wozu es trotzdem gut ist")[0])
        # dass der Assistent Licht machen kann, steht schon in den Grenzen
        for wort in ("Einmess-Assistent", "einschalten", "Bestätigung",
                     "niemand im Strahl", "LASER NOT-AUS"):
            self.assertIn(wort, kopf, wort)

    def test_anleitung_nennt_die_worte_der_oberflaeche(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from src.ui.visualizer import einmess_assistent as A
        flach = _flach(_abschnitt())
        self.assertIn(S.GRENZEN_KOMPAKT, flach)
        self.assertIn("„Sperrzonen planen“", flach)
        self.assertIn("„Sperrzonen planen…“", flach)
        for _k, knopf, *_rest in S.VORLAGEN:
            self.assertIn(f"„{knopf}“", flach, knopf)
        for wort in ("Draufsicht", "Seitenansicht", "Einrasten auf 0,25 m",
                     "„Rückgängig“ / „Wiederholen“", "„erreicht von Laser 1“", "„frei“",
                     "„ändern“", "„Feld einmessen…“", "„Zone löschen“",
                     "„Ich stelle den Laser selbst ein“",
                     "„Größtes Feld zeigen — schaltet den Laser ein“",
                     "„STOPP — Laser aus“", "„Abbrechen“", "„eingemessen am"):
            self.assertIn(wort, flach, wort)
        for i, schritt in enumerate(A.SCHRITTE, start=1):
            self.assertRegex(flach, rf"{i}\. \*\*{re.escape(schritt)}\.\*\*")
        self.assertIn(f"„{E.gegenprobe(4.0, 145.0, 'links')}“", flach)
        self.assertIn(f"mehr als {E.WINKEL_RUECKFRAGE_GRAD:g}°", flach)
        self.assertIn("nicht mit DMX-Werten", flach)

    def test_der_alte_dialog_wird_nicht_mehr_beschrieben(self):
        flach = _flach(_abschnitt())
        for alt in ("„Neue Zone“ legt", "Tabelle darunter", "Sperrzonen-Fenster",
                    "Mitte X/Z"):
            self.assertNotIn(alt, flach, alt)

    def test_bilder_liegen_bei_der_anleitung(self):
        a = _abschnitt()
        for name in ("las35_planer.png", "las35_assistent_schritt2.png",
                     "las35_assistent_schritt3.png"):
            self.assertIn(f"]({name})", a, name)
            self.assertTrue((_ANLEITUNG.parent / name).is_file(), name)

    def test_kein_schutzversprechen(self):
        for text in (_abschnitt(), _FRAGMENT.read_text(encoding="utf-8")):
            klein = text.lower()
            for wort in ("schützt", "geschützt", "abgesichert", "sicherheitsfunktion",
                         "verhindert", "überwacht"):
                self.assertNotIn(wort, klein, wort)
        fragment = _FRAGMENT.read_text(encoding="utf-8")
        self.assertIn("nur Anzeige", fragment.splitlines()[0])
        self.assertIn("Weiterhin nur Anzeige", fragment)
        self.assertIn("**nicht** ab", fragment)

    def test_backlog_zeile(self):
        # PROC-20: Der Eintrag liegt als Fragment unter backlog.d/, bis er
        # gesammelt ist; danach steht er als Zeile in BACKLOG.md.
        fragment = _REPO / "backlog.d" / "LAS-35.md"
        if fragment.exists():
            zeile = fragment.read_text(encoding="utf-8")
        else:
            backlog = (_REPO / "BACKLOG.md").read_text(encoding="utf-8")
            zeile = next(z for z in backlog.splitlines()
                         if z.startswith("| LAS-35 |"))
        self.assertIn("nur Anzeige", zeile)
        self.assertIn("Am echten Laser", zeile)


if __name__ == "__main__":
    unittest.main()
