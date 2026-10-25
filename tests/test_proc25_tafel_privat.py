"""PROC-25 — die Sitzungs-Tafel zieht in ein privates Tafel-Repo.

Bis 2026-10-25 lag ``SESSIONS.md`` auf dem Branch ``sessions`` des
OEFFENTLICHEN Repos. Jetzt arbeitet ``tools/session_claim.py`` auf einem
eigenen Klon des privaten Repos ``lightos-intern`` (Branch ``main``).

Gemessen wird ausschliesslich gegen Wegwerf-Repos im Temp-Ordner
(``git init --bare`` als Stellvertreter fuer GitHub) — nie gegen die echte
Tafel, nie mit Netz. Festgehalten wird:

* der Ort (``--tafel`` > ``LIGHTOS_TAFEL_REPO`` > ``<Projektordner>/lightos-intern``),
* der Abbruch ohne Klon samt Klon-Befehl — und dass es KEINEN stillen
  Rueckfall auf ``origin/sessions`` gibt,
* der Uebergangsweg ``LIGHTOS_TAFEL=alt``,
* ``umzug`` (trocken / echt / idempotent; ``sessions`` bleibt mit Hinweis),
* die Zugangsdaten-Sperre vor JEDEM Schreiben (Klarnamen erlaubt),
* ``entscheidung add/list/done`` und dass ein Claim ``ENTSCHEIDUNGEN.md`` stehen laesst,
* ``pr_bereit`` ohne Klon: Warnung statt gruen.
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_WURZEL, "tools"))

import session_claim as sc      # noqa: E402

# Attrappen-Zugangsdaten werden ZUSAMMENGESETZT, damit kein Geheimnis-Scanner
# (und kein Leser) eine echte Zeichenkette im Repo findet.
_FALSCH = {
    "ghp": "gh" + "p_" + "A1b2C3d4" * 5,
    "github_pat": "github" + "_pat_" + "11ABCDEFG0" * 3,
    "akia": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "key": "-----BEGIN " + "OPENSSH PRIVATE " + "KEY-----",
    "rsa": "-----BEGIN " + "RSA PRIVATE " + "KEY-----",
    "password": "pass" + "word=" + "hunter2",
    "kennwort": "Kenn" + "wort: " + "Sommer2026",
    "sk": "s" + "k-ant-" + "abcdefghij" * 3,
}


def _git(*args, repo=None):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"git {' '.join(args)}: {r.stderr}"
    return r.stdout.strip()


def _ruhig(fn, *args, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*args, **kw)
    return rc, out.getvalue(), err.getvalue()


class _Projekt(unittest.TestCase):
    """``<tmp>/projekt/repo`` (Code-Repo mit ``sessions``) und daneben
    ``<tmp>/projekt/lightos-intern`` (Klon des Tafel-Repos) — beide mit
    Bare-Repos im Temp-Ordner als ``origin``."""

    ALTE_TAFEL = {
        "claims": [{"item": "OUT-51", "sitzung": "B", "branch": "fix/out51",
                    "seit": "2026-10-25T08:00Z", "dateien": "src/a.py"}],
        "blocker": ["2026-10-25T07:00Z (A) Rig laeuft"],
        "verlauf": ["2026-10-25T08:00Z B claim OUT-51"],
    }

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lightos_proc25_")
        self.projekt = os.path.join(self.tmp, "projekt")
        os.makedirs(self.projekt)
        self.code_bare = self._bare("code.git")
        self.tafel_bare = self._bare("tafel.git")
        self.code = self._klon(self.code_bare, os.path.join(self.projekt, "repo"))
        self.klon = os.path.join(self.projekt, sc.TAFEL_ORDNER)
        self.namen = os.path.join(self.tmp, "klarnamen.txt")
        with open(self.namen, "w", encoding="utf-8") as f:
            f.write("Wilhelmine\n")
        umgebung = {k: v for k, v in os.environ.items()
                    if k not in ("LIGHTOS_TAFEL", "LIGHTOS_TAFEL_REPO")}
        umgebung["LIGHTOS_KLARNAMEN"] = self.namen
        self._env = mock.patch.dict(os.environ, umgebung, clear=True)
        self._env.start()

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _bare(self, name):
        pfad = os.path.join(self.tmp, name)
        _git("init", "--quiet", "--bare", pfad)
        return pfad

    def _klon(self, bare, pfad):
        _git("clone", "--quiet", bare, pfad)
        _git("config", "user.email", "test@example.invalid", repo=pfad)
        _git("config", "user.name", "Test", repo=pfad)
        return pfad

    def _tafel_klonen(self):
        return self._klon(self.tafel_bare, self.klon)

    def _alte_tafel_anlegen(self, tafel=None):
        ort = sc.TafelOrt(self.code, sc.BRANCH_ALT, True)
        self.assertTrue(sc._schreibe_dateien(
            ort, {sc.DATEI: sc.rendere(tafel or self.ALTE_TAFEL)}, None, "alt"))
        return _git("rev-parse", f"origin/{sc.BRANCH_ALT}", repo=self.code)

    def _main(self, *argv):
        return _ruhig(sc.main, ["--repo", self.code, *argv])

    def _sessions_spitze(self):
        return _git("ls-remote", self.code_bare, f"refs/heads/{sc.BRANCH_ALT}").split()[0]


class OrtTest(_Projekt):

    def test_vorgabe_ist_geschwister_von_repo(self):
        self.assertEqual(sc.tafel_vorgabe(self.code), self.klon)
        # Ein Worktree neben repo/ findet denselben Klon.
        wt = os.path.join(self.projekt, "wt-x")
        self.assertEqual(sc.tafel_vorgabe(wt), self.klon)

    def test_umgebung_vor_vorgabe_und_argument_vor_umgebung(self):
        anders = os.path.join(self.tmp, "woanders")
        with mock.patch.dict(os.environ, {"LIGHTOS_TAFEL_REPO": anders}):
            self.assertEqual(sc.tafel_pfad(self.code), anders)
            self.assertEqual(sc.tafel_pfad(self.code, self.klon), self.klon)
        self.assertEqual(sc.tafel_pfad(self.code), self.klon)

    def test_klon_aus_umgebung_wird_benutzt(self):
        anders = self._klon(self.tafel_bare, os.path.join(self.tmp, "anderswo"))
        with mock.patch.dict(os.environ, {"LIGHTOS_TAFEL_REPO": anders}):
            rc, out, err = self._main("claim", "QA-1", "--session", "A",
                                      "--files", "x.py")
        self.assertEqual(rc, 0, err)
        tafel, _ = sc.lade_tafel(anders)
        self.assertEqual([c["item"] for c in tafel["claims"]], ["QA-1"])

    def test_ohne_klon_abbruch_mit_klon_befehl(self):
        rc, out, err = self._main("list")
        self.assertEqual(rc, 3)
        self.assertIn(f"gh repo clone {sc.TAFEL_GITHUB} {self.klon}", err)
        self.assertIn("LIGHTOS_TAFEL_REPO", err)

    def test_kein_stiller_rueckfall_auf_sessions(self):
        """★ Die alte Tafel ist da, der Klon nicht: weder lesen noch schreiben
        darf auf ``sessions`` ausweichen."""
        vorher = self._alte_tafel_anlegen()
        rc, out, _ = self._main("list")
        self.assertEqual(rc, 3)
        self.assertNotIn("OUT-51", out)
        rc, _, _ = self._main("claim", "QA-2", "--session", "A", "--files", "x")
        self.assertEqual(rc, 3)
        self.assertEqual(self._sessions_spitze(), vorher, "sessions wurde beschrieben")

    def test_ordner_im_code_repo_ist_kein_klon(self):
        """Ein leerer Ordner IN einem anderen Repo ist fuer Git ein Teil davon —
        die Tafel landete sonst still im oeffentlichen Code-Repo."""
        drin = os.path.join(self.code, "lightos-intern")
        os.makedirs(drin)
        with self.assertRaises(sc.TafelFehlt) as e:
            sc.tafel_ort(self.code, drin)
        self.assertIn("gh repo clone", str(e.exception))

    def test_mit_klon_schreibt_auf_main_des_tafel_repos(self):
        self._tafel_klonen()
        rc, out, err = self._main("claim", "QA-3", "--session", "A", "--files", "x")
        self.assertEqual(rc, 0, err)
        self.assertTrue(_git("ls-remote", self.tafel_bare, "refs/heads/main"))
        self.assertEqual(_git("ls-remote", self.code_bare), "",
                         "das oeffentliche Repo wurde angefasst")


class AltModusTest(_Projekt):

    def test_alt_liest_und_schreibt_sessions_mit_warnung(self):
        self._alte_tafel_anlegen()
        with mock.patch.dict(os.environ, {"LIGHTOS_TAFEL": "alt"}):
            rc, out, err = self._main("list")
            self.assertEqual(rc, 0, err)
            self.assertIn("OUT-51", out)
            self.assertIn("LIGHTOS_TAFEL=alt", err)
            rc, _, err = self._main("claim", "QA-4", "--session", "A", "--files", "y")
        self.assertEqual(rc, 0, err)
        tafel, _ = sc.lade_tafel(sc.TafelOrt(self.code, sc.BRANCH_ALT, True))
        self.assertIn("QA-4", [c["item"] for c in tafel["claims"]])

    def test_alt_prueft_oeffentlich_privat_nicht(self):
        self._alte_tafel_anlegen()
        self._tafel_klonen()
        with mock.patch.dict(os.environ, {"LIGHTOS_TAFEL": "alt"}):
            rc, _, err = self._main("blocker", "Wilhelmine fragt", "--session", "A")
        self.assertEqual(rc, 2, "Klarname auf der OEFFENTLICHEN Tafel")
        rc, _, err = self._main("blocker", "Wilhelmine fragt", "--session", "A")
        self.assertEqual(rc, 0, f"Klarname im PRIVATEN Repo erlaubt: {err}")

    def test_alt_schreibt_nach_dem_umzug_nicht_mehr(self):
        self._alte_tafel_anlegen()
        self._tafel_klonen()
        self.assertEqual(self._main("umzug")[0], 0)
        spitze = self._sessions_spitze()
        with mock.patch.dict(os.environ, {"LIGHTOS_TAFEL": "alt"}):
            rc, out, err = self._main("claim", "QA-5", "--session", "A", "--files", "z")
        self.assertEqual(rc, 1)
        self.assertIn("umgezogen", out + err)
        self.assertEqual(self._sessions_spitze(), spitze)


class UmzugTest(_Projekt):

    def setUp(self):
        super().setUp()
        self.alt_spitze = self._alte_tafel_anlegen()
        self.alt_inhalt = _git("show", f"{self.alt_spitze}:{sc.DATEI}", repo=self.code)
        self._tafel_klonen()

    def test_trocken_schreibt_nichts(self):
        rc, out, err = self._main("umzug", "--trocken")
        self.assertEqual(rc, 0, err)
        self.assertIn("--trocken", out)
        self.assertIn("1 Claims", out)
        self.assertEqual(self._sessions_spitze(), self.alt_spitze)
        self.assertEqual(_git("ls-remote", self.tafel_bare), "")

    def test_echt_zieht_um_und_sessions_bleibt_mit_hinweis(self):
        rc, out, err = self._main("umzug", "--session", "A")
        self.assertEqual(rc, 0, err)
        # Neue Seite: Inhalt unveraendert + leere Entscheidungsliste.
        neu = sc.TafelOrt(self.klon)
        inhalt, _ = sc.lade_datei(neu, sc.DATEI)
        self.assertEqual(inhalt, self.alt_inhalt)
        e, _ = sc.lade_datei(neu, sc.DATEI_ENTSCHEIDUNGEN)
        self.assertEqual(sc.parse_entscheidungen(e)["offen"], [])
        self.assertIn("## Offen", e)
        # Alte Seite: Branch steht noch, letzter Commit = Hinweis, Eltern = alter Stand.
        spitze = self._sessions_spitze()
        self.assertNotEqual(spitze, self.alt_spitze)
        _git("fetch", "--quiet", "origin", repo=self.code)
        self.assertEqual(_git("rev-parse", f"{spitze}^", repo=self.code), self.alt_spitze)
        hinweis = _git("show", f"{spitze}:{sc.DATEI}", repo=self.code)
        self.assertIn(sc.UMZUG_MARKE, hinweis)
        self.assertIn("Historie bleibt hier", hinweis)
        self.assertEqual(sc.pruefe_oeffentlich(hinweis), [])
        self.assertEqual(sc.parse(hinweis)["claims"], [])
        # Danach arbeitet die Tafel normal weiter und sieht den alten Claim.
        rc, out, _ = self._main("list")
        self.assertEqual(rc, 0)
        self.assertIn("OUT-51", out)

    def test_zweiter_lauf_erkennt_den_umzug(self):
        self.assertEqual(self._main("umzug")[0], 0)
        alt, neu = self._sessions_spitze(), _git("ls-remote", self.tafel_bare)
        rc, out, err = self._main("umzug")
        self.assertEqual(rc, 0, err)
        self.assertIn("schon erledigt", out)
        self.assertEqual(self._sessions_spitze(), alt)
        self.assertEqual(_git("ls-remote", self.tafel_bare), neu)

    def test_halber_umzug_setzt_nur_noch_den_hinweis_und_nennt_nachtraege(self):
        neu = sc.TafelOrt(self.klon)
        self.assertTrue(sc._schreibe_dateien(neu, {sc.DATEI: self.alt_inhalt},
                                             None, "umzug: halb"))
        tafel = sc.parse(self.alt_inhalt)
        tafel["blocker"].append("2026-10-25T09:00Z (B) nach dem ersten Lauf")
        ort = sc.TafelOrt(self.code, sc.BRANCH_ALT, True)
        _, spitze = sc.lade_tafel(ort)
        self.assertTrue(sc._schreibe_dateien(ort, {sc.DATEI: sc.rendere(tafel)},
                                             spitze, "B schreibt noch alt"))
        rc, out, err = self._main("umzug")
        self.assertEqual(rc, 0, err)
        self.assertIn("nach dem ersten Lauf", err)
        self.assertIn(sc.UMZUG_MARKE, _git("show", f"{self._sessions_spitze()}:{sc.DATEI}",
                                           repo=self.code))

    def test_umzug_ohne_klon_bricht_ab(self):
        shutil.rmtree(self.klon)
        rc, out, err = self._main("umzug")
        self.assertEqual(rc, 3)
        self.assertIn("gh repo clone", err)
        self.assertEqual(self._sessions_spitze(), self.alt_spitze)

    def test_umzug_mit_zugangsdaten_auf_der_alten_tafel_bricht_ab(self):
        tafel = sc.parse(self.alt_inhalt)
        tafel["blocker"].append(f"2026-10-25T09:00Z (B) {_FALSCH['ghp']}")
        ort = sc.TafelOrt(self.code, sc.BRANCH_ALT, True)
        _, spitze = sc.lade_tafel(ort)
        # Von Hand an der Sperre vorbei (Plumbing), wie ein Altbestand.
        blob = sc._git("hash-object", "-w", "--stdin", eingabe=sc.rendere(tafel), repo=self.code)
        baum = sc._git("mktree", eingabe=f"100644 blob {blob}\t{sc.DATEI}\n", repo=self.code)
        commit = sc._git("commit-tree", baum, "-p", spitze, "-m", "hand", repo=self.code)
        sc._git("push", "--quiet", "origin", f"{commit}:refs/heads/{sc.BRANCH_ALT}", repo=self.code)
        rc, out, err = self._main("umzug")
        self.assertEqual(rc, 2)
        self.assertIn("Zugangsdaten", err)
        self.assertNotIn(_FALSCH["ghp"], out + err, "der Wert darf nie in der Meldung stehen")
        self.assertEqual(_git("ls-remote", self.tafel_bare), "")


class ZugangsdatenTest(_Projekt):

    def setUp(self):
        super().setUp()
        self._tafel_klonen()

    def test_jede_musterart_ist_rot(self):
        for art, wert in _FALSCH.items():
            with self.subTest(art=art):
                self.assertTrue(sc.pruefe_zugangsdaten(f"siehe {wert} bitte"), art)

    def test_harmlose_texte_bleiben_gruen(self):
        for text in ("Wilhelmine hat das Rig umgebaut",
                     "GITHUB_TOKEN kommt aus den Actions",
                     "Kennwort nie auf die Tafel",
                     "ghp ist ein Praefix", "sk-1 kurz", "AKIA kurz",
                     "secrets: sind in CI nicht noetig"):
            with self.subTest(text=text):
                self.assertEqual(sc.pruefe_zugangsdaten(text), [])

    def test_blocker_mit_zugangsdaten_wird_nicht_geschrieben(self):
        for art, wert in _FALSCH.items():
            with self.subTest(art=art):
                rc, out, err = self._main("blocker", f"Zugang: {wert}", "--session", "A")
                self.assertEqual(rc, 2)
                self.assertNotIn(wert, err)
        self.assertEqual(_git("ls-remote", self.tafel_bare), "", "es wurde geschrieben")

    def test_klarname_ist_im_privaten_repo_erlaubt(self):
        rc, out, err = self._main("blocker", "AN B: Wilhelmine baut um", "--session", "A")
        self.assertEqual(rc, 0, err)
        tafel, _ = sc.lade_tafel(self.klon)
        self.assertIn("Wilhelmine", tafel["blocker"][0])

    def test_sperre_greift_bei_jedem_schreiben_auch_beim_claim(self):
        """Steht von Hand ein Token auf der Tafel, schreibt auch ein Claim nicht."""
        tafel = sc.parse("")
        tafel["blocker"].append(f"2026-10-25T09:00Z (A) {_FALSCH['akia']}")
        blob = sc._git("hash-object", "-w", "--stdin", eingabe=sc.rendere(tafel), repo=self.klon)
        baum = sc._git("mktree", eingabe=f"100644 blob {blob}\t{sc.DATEI}\n", repo=self.klon)
        commit = sc._git("commit-tree", baum, "-m", "hand", repo=self.klon)
        sc._git("push", "--quiet", "origin", f"{commit}:refs/heads/main", repo=self.klon)
        rc, out, err = self._main("claim", "QA-6", "--session", "A", "--files", "x")
        self.assertEqual(rc, 2)
        self.assertIn("Zugangsdaten", err)
        self.assertEqual(_git("ls-remote", self.tafel_bare, "refs/heads/main").split()[0], commit)


class EntscheidungTest(_Projekt):

    def setUp(self):
        super().setUp()
        self._tafel_klonen()

    def test_add_list_done(self):
        self.assertEqual(self._main("entscheidung", "add", "Rig umbauen?",
                                    "--session", "A")[0], 0)
        self.assertEqual(self._main("entscheidung", "add", "Lizenz?",
                                    "--session", "B")[0], 0)
        rc, out, _ = self._main("entscheidung", "list")
        self.assertIn("E-1", out)
        self.assertIn("E-2", out)
        rc, out, err = self._main("entscheidung", "done", "e-1", "--session", "A",
                                  "--notiz", "ja, morgen")
        self.assertEqual(rc, 0, err)
        rc, out, _ = self._main("entscheidung", "list")
        self.assertNotIn("Rig umbauen", out)
        rc, out, _ = self._main("entscheidung", "list", "--alle")
        self.assertIn("ja, morgen", out)
        # Nummern werden nicht wiederverwendet.
        self._main("entscheidung", "add", "Neu?", "--session", "A")
        self.assertIn("E-3", self._main("entscheidung", "list")[1])

    def test_claim_laesst_entscheidungen_stehen(self):
        self._main("entscheidung", "add", "Bleibt?", "--session", "A")
        self.assertEqual(self._main("claim", "QA-7", "--session", "A",
                                    "--files", "x")[0], 0)
        e, _ = sc.lade_datei(sc.TafelOrt(self.klon), sc.DATEI_ENTSCHEIDUNGEN)
        self.assertIn("Bleibt?", e)

    def test_entscheidung_mit_zugangsdaten_abgelehnt(self):
        rc, _, err = self._main("entscheidung", "add", _FALSCH["password"],
                                "--session", "A")
        self.assertEqual(rc, 2)
        self.assertEqual(_git("ls-remote", self.tafel_bare), "")


class LeserTest(_Projekt):
    """Die gemeinsame Lesehilfe fuer backlog_ids/pr_bereit."""

    def test_lies_tafel_text_ohne_klon(self):
        tt = sc.lies_tafel_text(self.code)
        self.assertIsNone(tt.text)
        self.assertIn("gh repo clone", tt.klon_fehlt)

    def test_lies_tafel_text_mit_klon(self):
        self._tafel_klonen()
        self._main("claim", "DOC-77", "--session", "A", "--files", "x")
        tt = sc.lies_tafel_text(self.code)
        self.assertIsNone(tt.klon_fehlt)
        self.assertIn("DOC-77", tt.text)

    def test_backlog_ids_ueberspringt_ohne_klon_mit_hinweis(self):
        import backlog_ids as B
        with mock.patch.object(B, "_tafel_text", lambda: sc.lies_tafel_text(self.code)):
            ids, luecken = _ruhig(lambda: B.weitere_belegte_ids([]))[0]
        self.assertEqual((ids, luecken), (set(), []))

    def test_pr_bereit_ohne_klon_ist_warnung_nicht_gruen(self):
        import pr_bereit

        def gh_json(*args):
            if args[:2] == ("pr", "view"):
                return {"headRefOid": "abc", "headRefName": "fix/x", "title": "T",
                        "mergeable": "MERGEABLE", "isDraft": False}
            pfad = args[1] if len(args) > 1 else ""
            if pfad.endswith("/check-runs"):
                return {"check_runs": [{"conclusion": "success"}] * 3}
            if "/compare/" in pfad:
                return {"behind_by": 0}
            return {"commit": {"committer": {"date": "2026-10-01T08:00:00Z"}}}

        def fehlt():
            raise sc.TafelFehlt(self.klon)

        for argv, erwartet in ((["900"], 0), (["900", "--strict"], 1)):
            with self.subTest(argv=argv), \
                    mock.patch.object(pr_bereit, "_gh_json", gh_json), \
                    mock.patch.object(pr_bereit, "_lade_tafel", fehlt):
                rc, out, _ = _ruhig(pr_bereit.main, argv)
            self.assertEqual(rc, erwartet, out)
            self.assertIn(pr_bereit.CLAIM_UNGEPRUEFT, out)
            self.assertIn("gh repo clone", out)
            self.assertNotIn("✓ #900", out)
            self.assertNotIn("verfallenem Claim", out)


class CiBrauchtDieTafelNieTest(unittest.TestCase):
    """Bedingung der Verwalter-Sitzung: die oeffentliche CI liest die Tafel nie."""

    def test_kein_workflow_nennt_tafel_oder_tafel_repo(self):
        ordner = os.path.join(_WURZEL, ".github")
        for wurzel, _dirs, dateien in os.walk(ordner):
            for name in dateien:
                with open(os.path.join(wurzel, name), encoding="utf-8",
                          errors="replace") as f:
                    text = f.read()
                for wort in ("lightos-intern", "LIGHTOS_TAFEL", "SESSIONS.md",
                             "session_claim", "origin/sessions"):
                    self.assertNotIn(wort, text, f"{name} nennt {wort}")


if __name__ == "__main__":
    unittest.main()
