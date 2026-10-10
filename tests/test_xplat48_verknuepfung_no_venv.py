"""XPLAT-48: ``install.py --no-venv`` legt die Desktop-Verknuepfung auf das
Python, in das installiert wurde — nicht auf ein venv, das es nicht gibt.

Gefunden 2026-10-08 (Sitzung D) beim Codex-Hinweis zu DOC-62 (#960): die
Zusammenfassung nannte bei ``--no-venv`` das venv-Python (in #960 behoben),
und ``create_shortcut()`` zielte genauso auf ``venv\\Scripts\\pythonw.exe`` —
die Verknuepfung zeigte ins Leere.

Der Test legt KEINE echte Verknuepfung an: der PowerShell-Aufruf wird
abgefangen und nur sein Text geprueft.
"""
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _install():
    spec = importlib.util.spec_from_file_location(
        "_install_xplat48", os.path.join(REPO, "install.py"))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class VerknuepfungNoVenv(unittest.TestCase):

    def setUp(self):
        self.install = _install()
        self.tmp = tempfile.mkdtemp(prefix="xplat48_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # ein "System-Python" mit pythonw daneben; das venv gibt es NICHT
        self.sys_dir = os.path.join(self.tmp, "Python312")
        os.makedirs(self.sys_dir)
        for name in ("python.exe", "pythonw.exe"):
            open(os.path.join(self.sys_dir, name), "w").close()
        self.sys_python = os.path.join(self.sys_dir, "python.exe")
        self.kein_venv = Path(self.tmp) / "venv"

    def test_no_venv_nimmt_das_laufende_python(self):
        with mock.patch.object(self.install, "VENV_DIR", self.kein_venv):
            ziel = self.install.verknuepfung_python(False, self.sys_python)
        self.assertEqual(ziel, os.path.join(self.sys_dir, "pythonw.exe"))

    def test_ohne_pythonw_bleibt_python(self):
        os.remove(os.path.join(self.sys_dir, "pythonw.exe"))
        ziel = self.install.verknuepfung_python(False, self.sys_python)
        self.assertEqual(ziel, self.sys_python)

    def test_mit_venv_wie_bisher_das_venv(self):
        with mock.patch.object(self.install, "VENV_DIR", self.kein_venv):
            ziel = self.install.verknuepfung_python(True, self.sys_python)
        self.assertTrue(ziel.startswith(str(self.kein_venv)), ziel)

    @unittest.skipUnless(os.name == "nt", "Verknuepfung gibt es nur unter Windows")
    def test_create_shortcut_no_venv_zielt_auf_das_laufende_python(self):
        aufrufe = []
        with mock.patch.object(self.install, "VENV_DIR", self.kein_venv), \
                mock.patch.object(self.install.sys, "executable", self.sys_python), \
                mock.patch.object(self.install.subprocess, "run",
                                  side_effect=lambda *a, **k: aufrufe.append(a[0])), \
                mock.patch.object(self.install, "info"), \
                mock.patch.object(self.install, "warn"):
            self.install.create_shortcut(use_venv=False)
        self.assertEqual(len(aufrufe), 1, "genau ein PowerShell-Aufruf erwartet")
        befehl = " ".join(aufrufe[0])
        self.assertIn(f'TargetPath="{os.path.join(self.sys_dir, "pythonw.exe")}"', befehl)
        self.assertNotIn(str(self.kein_venv), befehl)

    def test_main_reicht_use_venv_an_die_verknuepfung(self):
        quelle = Path(REPO, "install.py").read_text(encoding="utf-8")
        self.assertIn("shortcut = create_shortcut(use_venv)", quelle)


if __name__ == "__main__":
    unittest.main()
