"""VIZ-111: die Anleitungen und das Bibliotheksschema nennen den Haken
„Zoom-Kanal umgekehrt (0 = weit)“ bzw. das Feld ``zoom_umgekehrt``.

Ohne Qt/DB — liest nur Text, damit es als Doku-Gate (tools/doku_gates.txt)
auch auf dem CI-Schnellweg laeuft.
"""
import os
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
#: muss mit ``abstrahlwinkel_feld.ZOOM_UMGEKEHRT_TEXT`` uebereinstimmen.
_TEXT = "Zoom-Kanal umgekehrt (0 = weit)"


def _lies(rel):
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class ZoomRichtungDokuTest(unittest.TestCase):

    def test_widget_text_stimmt_mit_der_doku(self):
        quelle = _lies("src/ui/widgets/abstrahlwinkel_feld.py")
        self.assertIn(f'ZOOM_UMGEKEHRT_TEXT = "{_TEXT}"', quelle)

    def test_anleitungen_nennen_den_haken(self):
        for rel in ("docs/anleitung_fixture_generator/ANLEITUNG_FIXTURE_GENERATOR.md",
                    "docs/anleitung_geraete_bibliothek/ANLEITUNG.md"):
            self.assertIn(_TEXT, _lies(rel), rel)

    def test_schema_nennt_das_feld(self):
        self.assertIn("| `zoom_umgekehrt` |", _lies("fixtures/bibliothek/SCHEMA.md"))


if __name__ == "__main__":
    unittest.main()
