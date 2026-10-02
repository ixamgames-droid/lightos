"""VIZ-66: LightOS liefert keine fremden 3D-Modelldateien mehr mit.

Bis VIZ-66 lagen unter ``src/ui/visualizer/assets/models/`` 19 Dateien, byte-gleich
aus QLC+ (Apache-2.0, Befund FM-55). Entscheidung des Projektinhabers 02.10.: sie
werden durch EIGENE, im Code erzeugte Geometrie ersetzt (three.js-Grundkoerper in
``scene_src/fixtures/builders.js`` und ``scene_src/stage/stage_objects.js``).

Dieser Waechter haelt drei Dinge fest:

* der Modell-Ordner ist weg und es liegen keine 3D-Modelldateien im Repo
  (``git ls-files`` — was nur lokal herumliegt, wird nicht verteilt);
* kein Szenen-Code laedt mehr ein Modell aus einer Datei (Loader, ``loadModel``,
  ``assets/models``) — sonst kaeme mit dem naechsten Overlay auch wieder eine Datei;
* die Loader-Scripts sind aus beiden Seiten verschwunden, die sie eingebunden haben.
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIS = ROOT / "src/ui/visualizer"

#: Endungen fuer 3D-Modelle/Meshes. Test-Fixtures duerften sie unter
#: ``tests/fixtures/`` tragen — derzeit gibt es keine.
MODELL_ENDUNGEN = (".dae", ".obj", ".fbx", ".gltf", ".glb", ".3ds", ".stl", ".ply", ".mtl")


def _repo_dateien():
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
        ).stdout.decode("utf-8", "replace")
        return [p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        # Ohne git (z. B. entpacktes Archiv): Dateibaum ohne venv/.git.
        return [
            p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
            if p.is_file() and not {"venv", ".git", "node_modules"} & set(p.parts)
        ]


class KeineFremdenModelleTest(unittest.TestCase):
    def test_modell_ordner_ist_weg(self):
        self.assertFalse((VIS / "assets/models").exists())

    def test_keine_modelldateien_im_repo(self):
        dateien = _repo_dateien()
        self.assertTrue(any(p.endswith("builders.js") for p in dateien),
                        "Gegenprobe: Dateiliste ist leer/falsch")
        treffer = [
            p for p in dateien
            if p.lower().endswith(MODELL_ENDUNGEN) and not p.startswith("tests/fixtures/")
        ]
        self.assertEqual(treffer, [], "3D-Modelldateien im Repo — VIZ-66: eigene Geometrie im Code")

    def test_szenen_code_laedt_keine_modelle(self):
        js = sorted((VIS / "scene_src").rglob("*.js"))
        self.assertGreater(len(js), 20, "Gegenprobe: scene_src nicht gefunden")
        verboten = ("loadModel(", "ColladaLoader", "OBJLoader", "GLTFLoader", "assets/models")
        funde = []
        for p in js:
            text = p.read_text(encoding="utf-8")
            for wort in verboten:
                # Kommentare duerfen die Geschichte erzaehlen, Code nicht.
                for zeile in text.splitlines():
                    code = zeile.split("//", 1)[0]
                    if wort in code:
                        funde.append(f"{p.relative_to(ROOT)}: {zeile.strip()}")
        self.assertEqual(funde, [])

    def test_seiten_binden_keine_loader_ein(self):
        for name in ("stage_scene.html", "gallery_render.html"):
            text = (VIS / name).read_text(encoding="utf-8")
            self.assertNotIn("Loader.js", text, name)


if __name__ == "__main__":
    unittest.main()
