"""PROC-18: Fremde Dateien im Repo brauchen Lizenztext und Urheberhinweis.

LightOS selbst hat keine Lizenz (Entscheidung des Projektinhabers), liefert aber
QLC+-Modelle (Apache-2.0) und three.js (MIT) mit. Beide Lizenzen verlangen, dass
der Lizenztext beiliegt. Befund aus FM-55: die Modelle lagen ohne jeden Hinweis
im Repo. Dieser Waechter haelt fest, dass jede Datei in den Fremd-Ordnern in
THIRD_PARTY_NOTICES.md steht und die Lizenztexte da sind.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"

#: Ordner, deren Inhalt komplett fremd ist -> jede Datei muss genannt sein.
FREMD_ORDNER = [
    ROOT / "src/ui/visualizer/assets/models",
    ROOT / "assets/vendor",
]
#: Einzelne fremde Dateien ausserhalb dieser Ordner.
FREMD_DATEIEN = [
    "src/ui/visualizer/three_local.js",
    "src/ui/visualizer/assets/ColladaLoader.js",
    "src/ui/visualizer/assets/OBJLoader.js",
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

    def test_lizenztexte_liegen_bei(self):
        apache = (ROOT / "licenses/Apache-2.0.txt").read_text(encoding="utf-8")
        self.assertIn("Apache License", apache)
        self.assertIn("Version 2.0, January 2004", apache)
        self.assertIn("4. Redistribution.", apache)
        mit = (ROOT / "licenses/MIT-three.js.txt").read_text(encoding="utf-8")
        self.assertIn("Permission is hereby granted", mit)
        self.assertIn("three.js authors", mit)
        for link in ("licenses/Apache-2.0.txt", "licenses/MIT-three.js.txt"):
            self.assertIn(link, self.text)


if __name__ == "__main__":
    unittest.main()
