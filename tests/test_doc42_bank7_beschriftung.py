"""DOC-42: die Beschriftung von Bank 7 der Event-Demo nennt nur, was da ist.

Der Chase-Builder ist seit 2026-06-30 entfernt (PR #116). Die Kopfzeile von
Bank 7 kuendigte ihn trotzdem noch an („Rechts: Cuelisten-Anzeige +
Chase-Builder.“) — in der fertigen Show steht rechts aber nur die
Cuelisten-Anzeige. Geprueft wird statisch am Generator, weil der beim Laufen
eine Show nach ``shows/`` schreibt.
"""
import ast
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_event_demo_2026.py")


def _beschriftungen(bank_name):
    with open(GENERATOR, encoding="utf-8") as fh:
        baum = ast.parse(fh.read())
    texte = []
    for k in ast.walk(baum):
        if (isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
                and k.func.id == "label" and len(k.args) >= 5
                and isinstance(k.args[4], ast.Name) and k.args[4].id == bank_name):
            try:
                texte.append(ast.literal_eval(k.args[0]))
            except ValueError:
                pass
    return texte


class Bank7BeschriftungTest(unittest.TestCase):

    def test_kopfzeile_gefunden(self):
        texte = _beschriftungen("B_MIX")
        self.assertTrue(any("BANK 7" in t for t in texte), texte)

    def test_kein_entfernter_chase_builder(self):
        for t in _beschriftungen("B_MIX"):
            self.assertNotIn("Chase-Builder", t)


if __name__ == "__main__":
    unittest.main()
