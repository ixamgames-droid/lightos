"""PROC-08 — die Blockerliste der Sitzungs-Tafel hat eine Grenze.

PROC-07 hat nur die LESE-Seite gekuerzt (`list --blocker N`); geschrieben wurde
unbegrenzt. Gemessen am 2026-10-01: 144 Blocker, 253 kB — und jeder `claim`
holt und schreibt die ganze Datei. Seit PROC-08 verfaellt ein Blocker beim
naechsten Schreiben nach ``BLOCKER_VERFALL`` (7 Tage). Gegen die echte Tafel
probehalber gerechnet: 144 -> 37 Eintraege, 253 -> 44 kB, und ``list --fuer``
liefert fuer A, B und C dieselben Briefe wie vorher.

Was NIE verfallen darf — und deshalb hier festgenagelt ist:

* ein Brief, den ein Adressat noch nicht gelesen hat,
* der letzte Eintrag jeder Sitzung (die Lesemarke von ``blocker_fuer``),
* ein Eintrag ohne lesbaren Zeitstempel.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import session_claim as sc      # noqa: E402

JETZT = sc.jetzt()


def _e(tage, sitzung, text):
    """Blocker-Eintrag im Format von ``cmd_blocker``, ``tage`` alt."""
    return f"{sc.stempel(JETZT - timedelta(days=tage))} ({sitzung}) {text}"


class VerfallsRegelTest(unittest.TestCase):

    def test_alter_gelesener_eintrag_faellt_junger_bleibt(self):
        b = [_e(10, "A", "alte Notiz"), _e(9, "A", "noch eine"),
             _e(1, "A", "frische Notiz")]
        self.assertEqual(sc.blocker_behalten(b, JETZT), b[2:])

    def test_grenze_liegt_bei_sieben_tagen(self):
        self.assertEqual(sc.BLOCKER_VERFALL, timedelta(days=7))
        b = [_e(6.9, "A", "knapp drin"), _e(7.1, "A", "knapp drueber"),
             _e(0, "A", "Lesemarke")]
        self.assertEqual(sc.blocker_behalten(b, JETZT), [b[0], b[2]])

    def test_ungelesener_brief_bleibt_auch_wenn_alt(self):
        b = [_e(20, "A", "A AN B: bitte X pruefen"), _e(1, "A", "anderes")]
        self.assertEqual(sc.blocker_behalten(b, JETZT), b)

    def test_gelesener_brief_verfaellt(self):
        b = [_e(20, "A", "A AN B: bitte X pruefen"),
             _e(19, "B", "B AN A: erledigt"),
             _e(1, "A", "neu"), _e(1, "B", "neu")]
        self.assertEqual(sc.blocker_behalten(b, JETZT), b[2:])

    def test_an_alle_bleibt_solange_eine_sitzung_schweigt(self):
        b = [_e(30, "C", "C fing an"),
             _e(20, "A", "A AN ALLE: neue Regel"),
             _e(10, "B", "B hat es gelesen"),
             _e(1, "A", "neu")]
        # C hat seit dem Brief nichts geschrieben -> offen.
        self.assertIn(b[1], sc.blocker_behalten(b, JETZT))
        b.append(_e(0, "C", "C auch"))
        self.assertNotIn(b[1], sc.blocker_behalten(b, JETZT))

    def test_letzter_eintrag_jeder_sitzung_bleibt(self):
        b = [_e(40, "B", "B alt"), _e(30, "B", "B zuletzt"), _e(1, "A", "A neu")]
        self.assertEqual(sc.blocker_behalten(b, JETZT), b[1:])

    def test_unlesbarer_stempel_bleibt(self):
        b = ["von Hand ohne Stempel", _e(30, "A", "alt"), _e(1, "A", "neu")]
        self.assertEqual(sc.blocker_behalten(b, JETZT), [b[0], b[2]])

    def test_lesemarke_briefe_an_jede_sitzung_unveraendert(self):
        b = [_e(30, "A", "A AN B: alt, gelesen"),
             _e(25, "B", "B: gelesen (Lesemarke)"),
             _e(20, "A", "A AN B: alt, UNGELESEN"),
             _e(15, "A", "A AN C: an C"),
             _e(2, "A", "A AN B: neu")]
        bleibt = sc.blocker_behalten(b, JETZT)
        for s in "ABC":
            with self.subTest(sitzung=s):
                self.assertEqual(sc.blocker_fuer(bleibt, s), sc.blocker_fuer(b, s))


def _git(*args, repo=None):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(args)}: {r.stderr}"
    return r.stdout.strip()


class SchreibSeiteTest(unittest.TestCase):
    """Gegen ein echtes Bare-Repo mit zwei Klonen — NIE die echte Tafel."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lightos_proc08_")
        bare = os.path.join(self.tmp, "origin.git")
        _git("init", "--quiet", "--bare", bare)
        self.a, self.b = (self._klon(bare, n) for n in ("a", "b"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _klon(self, bare, name):
        pfad = os.path.join(self.tmp, name)
        _git("clone", "--quiet", bare, pfad)
        _git("config", "user.email", "test@example.invalid", repo=pfad)
        _git("config", "user.name", "Test", repo=pfad)
        return pfad

    def test_jedes_schreiben_haelt_die_liste_begrenzt(self):
        alt = [_e(30 - i * 0.01, "A", f"alte Notiz {i}") for i in range(50)]
        tafel = {"claims": [], "blocker": alt + [_e(1, "A", "frisch")], "verlauf": []}
        self.assertTrue(sc.schreibe_tafel(self.a, tafel, None, "start"))

        gelesen, _ = sc.lade_tafel(self.b)
        self.assertEqual(gelesen["blocker"], [tafel["blocker"][-1]])
        self.assertTrue(any("50 Blocker verfallen" in v for v in gelesen["verlauf"]),
                        gelesen["verlauf"])

    def test_der_blocker_befehl_raeumt_einen_alten_stand_auf(self):
        """Eine Tafel von vor PROC-08 (ungekuerzt) wird beim naechsten
        gewoehnlichen ``blocker``-Aufruf begrenzt."""
        alt = {"claims": [], "verlauf": [],
               "blocker": [_e(30, "A", "alt"), _e(29, "A", "A zuletzt")]}
        # Stand OHNE Verfall hinlegen — so, wie ihn das alte Werkzeug schrieb.
        blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=self.a,
                              input=sc.rendere(alt).encode(), capture_output=True,
                              check=True).stdout.decode().strip()
        baum = subprocess.run(["git", "mktree"], cwd=self.a, capture_output=True, check=True,
                              input=f"100644 blob {blob}\t{sc.DATEI}\n".encode()
                              ).stdout.decode().strip()
        commit = _git("commit-tree", baum, "-m", "alter Stand", repo=self.a)
        _git("push", "--quiet", "origin", f"{commit}:refs/heads/{sc.BRANCH}", repo=self.a)

        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            rc = sc.main(["--repo", self.b, "blocker", "--session", "B", "B neu"])
        self.assertEqual(rc, 0)
        texte = [x.split(") ", 1)[1] for x in sc.lade_tafel(self.a)[0]["blocker"]]
        # „alt" verfaellt; „A zuletzt" bleibt als Lesemarke von A.
        self.assertEqual(texte, ["A zuletzt", "B neu"])

    def test_kopf_nennt_regel_und_historie(self):
        text = sc.rendere({"claims": [], "blocker": [], "verlauf": []})
        self.assertIn("PROC-08", text)
        self.assertIn("git log -p origin/sessions", text)


class DokuTest(unittest.TestCase):

    def test_coordination_nennt_den_verfall(self):
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "COORDINATION.md")
        with open(pfad, encoding="utf-8") as f:
            text = f.read()
        for stichwort in ("PROC-08", "7 Tagen", "Lesemarke", "git log -p origin/sessions"):
            self.assertTrue(stichwort in text, f"COORDINATION.md nennt {stichwort!r} nicht")


if __name__ == "__main__":
    unittest.main()
