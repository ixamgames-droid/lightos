"""DOC-30: die Kopfzeile von Bank 8 der Event-Demo sagt, worauf die Kacheln wirken.

Die Farb-Kacheln der Bank „Programmer" zielen auf den PROGRAMMER
(``ColorTarget.PROGRAMMER``; leer = alle Geraete), nicht auf die Auswahl aus
Reihe 0. Die Kopfzeile versprach „R2: Farb-Kacheln auf Selektion" — wer eine
Gruppe waehlte und eine Kachel drueckte, faerbte trotzdem alle Geraete.
Geprueft wird statisch am Generator, weil der beim Laufen eine Show nach
``shows/`` schreibt.
"""
import ast
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_event_demo_2026.py")


def _baum():
    with open(GENERATOR, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _beschriftungen(bank_name):
    texte = []
    for k in ast.walk(_baum()):
        if (isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
                and k.func.id == "label" and len(k.args) >= 5
                and isinstance(k.args[4], ast.Name) and k.args[4].id == bank_name):
            try:
                texte.append(ast.literal_eval(k.args[0]))
            except ValueError:
                pass
    return texte


def _kachel_ziele(bank_name):
    ziele = []
    for k in ast.walk(_baum()):
        if (isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
                and k.func.id == "color_tile" and len(k.args) >= 3
                and isinstance(k.args[2], ast.Name) and k.args[2].id == bank_name):
            for kw in k.keywords:
                if kw.arg == "target":
                    ziele.append(ast.unparse(kw.value))
    return ziele


class Bank8BeschriftungTest(unittest.TestCase):

    def test_kopfzeile_gefunden(self):
        self.assertTrue(any("BANK 8" in t for t in _beschriftungen("B_PROG")))

    def test_kacheln_zielen_auf_den_programmer(self):
        """Voraussetzung der Beschriftung — aendert sich das, muss sie mit."""
        ziele = _kachel_ziele("B_PROG")
        self.assertTrue(ziele)
        self.assertEqual(set(ziele), {"ColorTarget.PROGRAMMER"})

    def test_kopfzeile_nennt_den_programmer_nicht_die_selektion(self):
        kopf = next(t for t in _beschriftungen("B_PROG") if "BANK 8" in t)
        self.assertNotIn("Selektion", kopf)
        self.assertIn("Farb-Kacheln über den Programmer", kopf)
        self.assertIn("leer = alle Geräte", kopf)


if __name__ == "__main__":
    unittest.main()
