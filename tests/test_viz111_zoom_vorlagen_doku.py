"""VIZ-111 (4): die Effekt-Anleitung nennt die drei Zoom-Vorlagen und den
Ausgegraut-Hinweis — mit denselben Namen wie der Assistent.

Ohne Qt/DB — liest nur Text, damit es als Doku-Gate (tools/doku_gates.txt)
auch auf dem CI-Schnellweg laeuft.
"""
import os
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_NAMEN = ("Zoom-Puls", "Zoom-Welle", "Zoom im Takt")
_HINWEIS = "kein Gerät mit Zoom-Kanal gepatcht"


def _lies(rel):
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class ZoomVorlagenDokuTest(unittest.TestCase):

    def test_assistent_fuehrt_die_namen(self):
        quelle = _lies("src/ui/widgets/effect_wizard.py")
        for n in _NAMEN:
            self.assertIn(f'"{n}"', quelle, n)
        self.assertIn(_HINWEIS, quelle)

    def test_anleitung_nennt_vorlagen_und_hinweis(self):
        doku = _lies("docs/EFFEKTE.md")
        for n in _NAMEN:
            self.assertIn(f"**{n}**", doku, n)
        self.assertIn(_HINWEIS, doku)


if __name__ == "__main__":
    unittest.main()
