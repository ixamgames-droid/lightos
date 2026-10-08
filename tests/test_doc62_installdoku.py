"""DOC-62: die Installationsdoku nennt die Windows-Fallen, auf die ein frischer
Testrechner gelaufen ist (Sitzung D, Windows 11, 2026-10-08).

Gemessen, nicht vermutet:

* ``python install.py`` nahm die Version, die im PATH zuerst stand (3.14), obwohl
  3.12 gewuenscht und installiert war — der Launcher ``py -3.12`` waehlt sie.
* Das Test-Gate lief nach der Installation laut INSTALL.md 0/834 rot: jedes
  Segment endete mit ``No module named pytest``, weil ``requirements-dev.txt``
  nirgends genannt war. CONTRIBUTING.md empfahl zudem ``pytest tests/ -v`` —
  genau den Aufruf, den AGENTS.md verbietet — und ein Paket-Set ohne das
  Pflicht-Plugin ``pytest-timeout``.
* ``install.py`` nannte im Docstring eine Startmenue-Verknuepfung, die es nie
  anlegt, und legte die Desktop-Verknuepfung ohne jeden Hinweis an.
"""
import ast
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lies(name: str) -> str:
    with open(os.path.join(REPO, name), encoding="utf-8") as f:
        return f.read()


class InstallDokuTest(unittest.TestCase):

    def test_install_md_nennt_den_py_launcher(self):
        t = _lies("INSTALL.md")
        self.assertRegex(t, r"py -3\.\d+ install\.py")
        self.assertIn("py -0p", t)

    def test_install_md_nennt_die_test_abhaengigkeiten(self):
        t = _lies("INSTALL.md")
        self.assertIn("requirements-dev.txt", t)
        # Das Symptom, an dem man den Fall erkennt, steht dabei.
        self.assertIn("No module named pytest", t)

    def test_contributing_nutzt_das_gate_statt_pytest_direkt(self):
        t = _lies("CONTRIBUTING.md")
        self.assertIn("requirements-dev.txt", t)
        self.assertIn("verify_segmented.ps1", t)
        self.assertIn("verify_loop.sh", t)
        # Kein direkter Gesamtlauf mehr als Anleitung (Codezeile oder Inline-Code).
        self.assertNotRegex(t, r"(?m)^\s*pytest tests/")
        self.assertNotIn("`pytest tests/ -v`", t)

    def test_requirements_dev_enthaelt_was_die_doku_verspricht(self):
        t = _lies("requirements-dev.txt")
        for paket in ("pytest", "pytest-timeout", "hypothesis"):
            with self.subTest(paket):
                self.assertRegex(t, rf"(?mi)^{re.escape(paket)}\s*[<>=~!]")

    def test_install_py_nennt_keine_verknuepfung_die_es_nicht_anlegt(self):
        quelle = _lies("install.py")
        doc = ast.get_docstring(ast.parse(quelle)) or ""
        code = quelle.replace(doc, "")
        nennt_startmenue = re.search(r"Start-?Men\w*\\", doc)
        legt_startmenue_an = re.search(r"Start Menu|StartMenu|\\Programs\\|CSIDL_PROGRAMS", code)
        self.assertFalse(nennt_startmenue and not legt_startmenue_an,
                         "install.py nennt eine Startmenue-Verknuepfung, legt aber keine an")
        # Die Desktop-Verknuepfung entsteht ohne Rueckfrage — der Ausweg steht dabei.
        self.assertIn("--no-shortcut", doc)


if __name__ == "__main__":
    unittest.main()
