"""TOOL-2: keine Windows-Binaerdateien im oeffentlichen Repo.

Bis 2026-10-02 lagen unter ``tools/gource/`` 17 MB Fremd-Binaerdateien
(``gource.exe`` + rund 30 DLLs, GPL/LGPL u. a.) — nur fuer das
Entwickler-Werkzeug „Code-Film“, auf Linux gar nicht benutzbar. Gource wird
jetzt installiert statt mitgeliefert; ``Code-Film.bat`` sucht es im PATH.
"""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_BINAER = (".exe", ".dll")


def _binaerdateien(wurzel=ROOT):
    """Die GETRACKTEN ``.exe``/``.dll`` unter ``wurzel`` (``git ls-files``).

    Review #915: frueher ``os.walk`` — das schlug bei einer ungetrackten
    ``gource.exe`` im Arbeitsbaum an (lokal installiert, gitignored) und
    haette eine getrackte in einem ausgeblendeten Ordner uebersehen. Gefragt
    ist, was im oeffentlichen Repo LIEGT, also was git kennt."""
    aus = subprocess.run(["git", "ls-files", "-z"], cwd=wurzel, check=True,
                         capture_output=True).stdout.decode("utf-8")
    return sorted(p for p in aus.split("\0")
                  if p and p.lower().endswith(_BINAER))


class KeineBinaerdateienTest(unittest.TestCase):

    def setUp(self):
        if shutil.which("git") is None or not (ROOT / ".git").exists():
            self.skipTest("kein git-Arbeitsbaum")

    def test_kein_exe_und_keine_dll_im_repo(self):
        self.assertEqual(_binaerdateien(), [])

    def test_waechter_unterscheidet_getrackt_und_ungetrackt(self):
        """Gegenprobe in einem Wegwerf-Repo: eine ungetrackte ``.exe`` ist
        kein Befund, dieselbe Datei nach ``git add`` schon."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="lightos_tool2_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        (tmp / "tools").mkdir()
        (tmp / "tools" / "gource.exe").write_bytes(b"MZ")
        self.assertEqual(_binaerdateien(tmp), [], "ungetrackt darf nicht rot sein")
        subprocess.run(["git", "add", "tools/gource.exe"], cwd=tmp, check=True)
        self.assertEqual(_binaerdateien(tmp), ["tools/gource.exe"],
                         "getrackt muss rot sein")

    def test_code_film_bat_nutzt_installiertes_gource(self):
        bat = (ROOT / "Code-Film.bat").read_text(encoding="utf-8")
        self.assertNotIn("tools\\gource", bat)
        self.assertIn("where gource", bat, "ohne Pruefung kommt nur ein kryptischer Fehler")
        self.assertIn("gource.io", bat, "der Hinweis muss sagen, woher Gource kommt")


if __name__ == "__main__":
    unittest.main()
