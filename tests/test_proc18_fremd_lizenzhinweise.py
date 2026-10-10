"""PROC-18: Fremde Dateien im Repo brauchen Lizenztext und Urheberhinweis.

LightOS selbst hat keine Lizenz (Entscheidung des Projektinhabers), liefert aber
three.js (MIT) mit; die Lizenz verlangt, dass der Lizenztext beiliegt. Befund aus
FM-55: fremde Dateien lagen ohne jeden Hinweis im Repo. Dieser Waechter haelt
fest, dass jede Datei in den Fremd-Ordnern in THIRD_PARTY_NOTICES.md steht und
die Lizenztexte da sind.

VIZ-66: die frueheren QLC+-Modelle (Apache-2.0) sind durch eigene Geometrie
ersetzt und mitsamt Apache-Lizenztext entfernt. Dass keine Modelldateien
zurueckkommen, prueft ``test_viz66_keine_fremden_modelle.py``.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"

#: Ordner, deren Inhalt komplett fremd ist -> jede Datei muss genannt sein.
FREMD_ORDNER = [
    ROOT / "assets/vendor",
]
#: Einzelne fremde Dateien ausserhalb dieser Ordner.
FREMD_DATEIEN = [
    "src/ui/visualizer/three_local.js",
    "src/web/static/socket.io.min.js",        # WEB-06
]


class FremdLizenzhinweiseTest(unittest.TestCase):
    def setUp(self):
        self.text = NOTICES.read_text(encoding="utf-8")

    def test_jede_fremde_datei_ist_genannt(self):
        fehlt = []
        for ordner in FREMD_ORDNER:
            for p in sorted(ordner.rglob("*")):
                if not p.is_file():
                    continue
                rel_ordner = p.relative_to(ordner).as_posix()
                rel_root = p.relative_to(ROOT).as_posix()
                if rel_ordner not in self.text and rel_root not in self.text:
                    fehlt.append(rel_root)
        for rel in FREMD_DATEIEN:
            if rel not in self.text:
                fehlt.append(rel)
        self.assertEqual(fehlt, [], "fremde Dateien ohne Eintrag in THIRD_PARTY_NOTICES.md")

    def test_fremd_ordner_sind_nicht_leer(self):
        # Gegenprobe: ein verschobener Ordner liesse den Waechter leer gruen werden.
        for ordner in FREMD_ORDNER:
            self.assertTrue(any(p.is_file() for p in ordner.rglob("*")), ordner)

    def test_fremd_dateien_existieren(self):
        # Gegenprobe: eine umbenannte Datei liesse ihren Eintrag ins Leere zeigen.
        for rel in FREMD_DATEIEN:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_lizenztexte_liegen_bei(self):
        mit = (ROOT / "licenses/MIT-three.js.txt").read_text(encoding="utf-8")
        self.assertIn("Permission is hereby granted", mit)
        self.assertIn("three.js authors", mit)
        self.assertIn("licenses/MIT-three.js.txt", self.text)

    def test_jeder_lizenztext_gehoert_zu_einem_eintrag(self):
        # VIZ-66: ein Lizenztext ohne Komponente (z. B. Apache-2.0 nach dem
        # Entfernen der QLC+-Modelle) behauptete eine Fremd-Datei, die es nicht gibt.
        for p in sorted((ROOT / "licenses").iterdir()):
            self.assertIn(f"licenses/{p.name}", self.text, p.name)


if __name__ == "__main__":
    unittest.main()
