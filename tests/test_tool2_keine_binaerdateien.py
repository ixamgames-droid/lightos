"""TOOL-2: keine Windows-Binaerdateien im oeffentlichen Repo.

Bis 2026-10-02 lagen unter ``tools/gource/`` 17 MB Fremd-Binaerdateien
(``gource.exe`` + rund 30 DLLs, GPL/LGPL u. a.) — nur fuer das
Entwickler-Werkzeug „Code-Film“, auf Linux gar nicht benutzbar. Gource wird
jetzt installiert statt mitgeliefert; ``Code-Film.bat`` sucht es im PATH.
"""
import os
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_BINAER = (".exe", ".dll")
_NICHT_DURCHSUCHEN = {"venv", ".venv", "node_modules", "__pycache__",
                      ".pytest_segments", "build", "dist"}


def _binaerdateien():
    treffer = []
    for wurzel, ordner, dateien in os.walk(ROOT):
        ordner[:] = [o for o in ordner
                     if not o.startswith(".") and o not in _NICHT_DURCHSUCHEN]
        for d in dateien:
            if d.lower().endswith(_BINAER):
                treffer.append(pathlib.Path(wurzel, d).relative_to(ROOT).as_posix())
    return sorted(treffer)


class KeineBinaerdateienTest(unittest.TestCase):

    def test_kein_exe_und_keine_dll_im_repo(self):
        self.assertEqual(_binaerdateien(), [])

    def test_code_film_bat_nutzt_installiertes_gource(self):
        bat = (ROOT / "Code-Film.bat").read_text(encoding="utf-8")
        self.assertNotIn("tools\\gource", bat)
        self.assertIn("where gource", bat, "ohne Pruefung kommt nur ein kryptischer Fehler")
        self.assertIn("gource.io", bat, "der Hinweis muss sagen, woher Gource kommt")


if __name__ == "__main__":
    unittest.main()
