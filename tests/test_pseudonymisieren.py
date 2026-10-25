"""PRIV-06 — tools/pseudonymisieren.py: ``--nur``, Protokolle, Wortgrenzen.

Gearbeitet wird in einem frischen tmp-Git-Repo mit einem KUENSTLICHEN Namen —
der echte steht nirgends im Repo, auch nicht in diesem Test.
"""
import importlib.util
import os
import subprocess
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NAME = "Kasi" + "mirus"


def _werkzeug():
    spec = importlib.util.spec_from_file_location(
        "_pseudonymisieren_test", os.path.join(_REPO, "tools", "pseudonymisieren.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PseudonymisierenTest(unittest.TestCase):

    def setUp(self):
        self.pz = _werkzeug()
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        self.dateien = {
            "BACKLOG.md": f"| X-1 | Wunsch von {_NAME} | {_NAME}s Idee |\n",
            "BACKLOG_ARCHIVE.md": f"{_NAME} hat entschieden\n",
            "backlog.d/X-2.md": f"_{_NAME}-Auftrag: …_ {_NAME.upper()} "
                                f"{_NAME.lower()} test.lshow {_NAME}son\n",
            "backlog.dx/Y.md": f"{_NAME}\n",
            "docs/ANLEITUNG.md": f"{_NAME} liest das\n",
            "CHANGELOG.md": f"{_NAME}\n",
        }
        for rel, inhalt in self.dateien.items():
            pfad = os.path.join(self.repo, rel)
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(inhalt)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _lies(self, rel):
        with open(os.path.join(self.repo, rel), encoding="utf-8") as f:
            return f.read()

    def _lauf(self, **kw):
        self.pz.lauf(self.repo, _NAME, "Robin", True, kw.get("protokolle", False),
                     kw.get("nur"))

    def test_nur_beschraenkt_auf_dateien_und_ordner(self):
        self._lauf(nur=["BACKLOG.md", "backlog.d/"])
        self.assertNotIn(_NAME, self._lies("BACKLOG.md"))
        self.assertIn("Robins Idee", self._lies("BACKLOG.md"))
        self.assertIn(_NAME, self._lies("docs/ANLEITUNG.md"))
        # Praefix je Pfadsegment: backlog.d trifft backlog.dx/ nicht.
        self.assertIn(_NAME, self._lies("backlog.dx/Y.md"))

    def test_protokoll_nur_wenn_beim_namen_genannt(self):
        self._lauf(nur=["BACKLOG.md", "backlog.d"])
        self.assertIn(_NAME, self._lies("BACKLOG_ARCHIVE.md"))
        self._lauf(nur=["BACKLOG_ARCHIVE.md"])
        self.assertEqual(self._lies("BACKLOG_ARCHIVE.md"), "Robin hat entschieden\n")
        self.assertIn(_NAME, self._lies("CHANGELOG.md"))

    def test_wortgrenzen_unterstrich_und_schreibweise(self):
        self._lauf(nur=["backlog.d"])
        self.assertEqual(self._lies("backlog.d/X-2.md"),
                         f"_Robin-Auftrag: …_ ROBIN robin test.lshow {_NAME}son\n")

    def test_ohne_nur_bleibt_alles_wie_bisher(self):
        self._lauf()
        self.assertNotIn(_NAME, self._lies("docs/ANLEITUNG.md"))
        self.assertIn(_NAME, self._lies("BACKLOG_ARCHIVE.md"))
        self.assertIn(_NAME, self._lies("CHANGELOG.md"))

    def test_pruefen_schreibt_nichts(self):
        self.pz.lauf(self.repo, _NAME, "Robin", False, True, None)
        for rel, inhalt in self.dateien.items():
            self.assertEqual(self._lies(rel), inhalt)


if __name__ == "__main__":
    unittest.main()
