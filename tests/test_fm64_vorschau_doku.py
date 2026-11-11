"""FM-64 (Teil 2): die Anleitungen beschreiben die 3D-Vorschau im
Fixture-Editor und -Generator — mit derselben Knopf-Beschriftung wie der Code.

Ohne Qt/DB — liest nur Text, damit es als Doku-Gate (tools/doku_gates.txt)
auch auf dem CI-Schnellweg laeuft.
"""
import os
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_ANLEITUNGEN = ("docs/anleitung_fixture_generator/ANLEITUNG_FIXTURE_GENERATOR.md",
                "docs/anleitung_geraete_bibliothek/ANLEITUNG.md")


def _lies(rel):
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class VorschauDokuTest(unittest.TestCase):

    def test_knopf_heisst_wie_in_der_doku(self):
        quelle = _lies("src/ui/widgets/fixture_vorschau_3d.py")
        self.assertIn('KNOPF_ZEIGEN = "▶ Vorschau zeigen"', quelle)

    def test_anleitungen_beschreiben_die_vorschau(self):
        for rel in _ANLEITUNGEN:
            text = _lies(rel)
            with self.subTest(rel=rel):
                for marke in ("**Vorschau zeigen**", "**Zoom:**", "**Gobo:**",
                              "**Farbe:**", "WebGL"):
                    self.assertIn(marke, text, f"{rel}: {marke} fehlt")


if __name__ == "__main__":
    unittest.main()
