"""DOC-53: „Linie (Spider Wippe)" der Hochzeit-Show stand still.

Dieselbe Falle wie DOC-37 in der Event-Demo: ``EfxAlgorithm.LINE`` laeuft auf
der PAN-Achse, ein Spider hat keinen Pan, nur zwei Tilt-Motoren. Ohne Drehung
um 90 Grad bleiben beide Tilts auf 128 — gemessen am Render-Pfad in
``tests/test_doc37_spider_wippe.py`` (dort die Positivkontrolle mit 0 Grad).

Geprueft wird statisch am Generator, weil der beim Laufen eine Show nach
``shows/`` schreibt und ein nur lokal importiertes Spider-Profil braucht.
"""
import ast
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "tools", "build_hochzeit_komplett.py")


def _baum():
    with open(GENERATOR, encoding="utf-8") as fh:
        return ast.parse(fh.read())


class HochzeitLinieTest(unittest.TestCase):

    def test_linie_ist_senkrecht_gestellt(self):
        aufruf = next((k for k in ast.walk(_baum())
                       if isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
                       and k.func.id == "efx" and k.args
                       and isinstance(k.args[0], ast.Constant)
                       and k.args[0].value == "Linie (Spider Wippe)"), None)
        self.assertIsNotNone(aufruf)
        self.assertEqual(ast.unparse(aufruf.args[1]), "EfxAlgorithm.LINE")
        rot = {kw.arg: kw.value for kw in aufruf.keywords}.get("rotation")
        self.assertIsNotNone(rot, "ohne rotation laeuft die Linie auf der fehlenden Pan-Achse")
        self.assertEqual(ast.literal_eval(rot), 90.0)

    def test_helfer_reicht_rotation_durch(self):
        helfer = next(k for k in ast.walk(_baum())
                      if isinstance(k, ast.FunctionDef) and k.name == "efx")
        self.assertIn("rotation", [a.arg for a in helfer.args.args])
        self.assertIn("e.rotation = rotation", ast.unparse(helfer))


if __name__ == "__main__":
    unittest.main()
