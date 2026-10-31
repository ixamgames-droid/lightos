"""TOOL-29: Die Namenspruefung startet git nur einmal je Prozess.

Herkunft: Sitzung B (Windows-ARM, 29.10.2026). ``pruefe_oeffentlich`` fragte je
Backlog-Zeile ``git rev-parse --git-common-dir`` ab — rund 2450 Prozessstarts,
182 s, und ``test_keine_privaten_dateien`` lief dort ins Zeitlimit.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import session_claim as sc  # noqa: E402


class EinGitJeProzessTest(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.pop("LIGHTOS_KLARNAMEN", None)
        sc._GIT_KLARNAMEN_ORT = sc._UNBEKANNT

    def tearDown(self):
        sc._GIT_KLARNAMEN_ORT = sc._UNBEKANNT
        if self._env is not None:
            os.environ["LIGHTOS_KLARNAMEN"] = self._env

    def test_viele_pruefungen_ein_git_aufruf(self):
        echt = subprocess.run
        aufrufe = []

        def zaehle(cmd, *a, **k):
            if list(cmd[:2]) == ["git", "rev-parse"]:
                aufrufe.append(cmd)
            return echt(cmd, *a, **k)

        with mock.patch.object(sc.subprocess, "run", side_effect=zaehle):
            for i in range(50):
                sc.pruefe_oeffentlich(f"Zeile {i} ohne Befund")
        self.assertEqual(len(aufrufe), 1, aufrufe)

    def test_liste_wird_trotzdem_frisch_gelesen(self):
        """Gemerkt wird nur der Ort — eine geaenderte Namensliste wirkt sofort."""
        with tempfile.TemporaryDirectory() as tmp:
            ort = os.path.join(tmp, "klarnamen.txt")
            with mock.patch.object(sc, "_git_klarnamen_datei", return_value=ort), \
                 mock.patch.object(sc, "klarnamen_datei", return_value=os.path.join(tmp, "fehlt.txt")):
                self.assertEqual(sc.pruefe_oeffentlich("Zorbald war da"), [])
                with open(ort, "w", encoding="utf-8") as f:
                    f.write("Zorbald\n")
                self.assertTrue(sc.pruefe_oeffentlich("Zorbald war da"))

    def test_testumgebung_liest_keinen_git_ort(self):
        with mock.patch.dict(os.environ, {"LIGHTOS_KLARNAMEN": "x.txt"}):
            self.assertIsNone(sc._git_klarnamen_datei())


if __name__ == "__main__":
    unittest.main()
