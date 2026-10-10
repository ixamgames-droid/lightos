"""PROC-01 — der Belegzettel fuer parallele Sitzungen muss ein Rennen entscheiden.

★ Der Punkt dieses Werkzeugs ist **nicht**, dass es eine Markdown-Tabelle
pflegt — das koennte man von Hand. Der Punkt ist, dass zwei Sitzungen, die im
selben Moment dasselbe Item nehmen wollen, hinterher **wissen**, wer es hat.
Genau das kann eine Pruefung allein nicht leisten: beide lesen „frei".

Entschieden wird es erst am Push. Deshalb testet die zentrale Klasse hier
gegen ein **echtes Bare-Repo** mit **zwei echten Klonen** — eine Attrappe
koennte den Fall gar nicht zeigen, weil sie das Fast-Forward-Verhalten von Git
nachbauen muesste, also genau das, was hier bewiesen werden soll.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import session_claim as sc      # noqa: E402


def _git(*args, repo=None, eingabe=None):
    r = subprocess.run(["git", *args], cwd=repo, input=eingabe,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"git {' '.join(args)}: {r.stderr}"
    return r.stdout.strip()


class TafelFormatTest(unittest.TestCase):
    """Lesen und Schreiben muessen sich gegenseitig ueberleben."""

    def test_rundreise(self):
        tafel = {
            "claims": [{"item": "OUT-51", "sitzung": "B",
                        "branch": "fix/out51", "seit": "2026-08-06T14:10Z",
                        "dateien": "src/core/dmx/output_manager.py"}],
            "blocker": ["2026-08-06T14:00Z (A) Rig ist in Benutzung"],
            "verlauf": ["2026-08-06T14:10Z B claim OUT-51"],
        }
        wieder = sc.parse(sc.rendere(tafel))
        self.assertEqual(wieder["claims"], tafel["claims"])
        self.assertEqual(wieder["blocker"], tafel["blocker"])
        self.assertEqual(wieder["verlauf"], tafel["verlauf"])

    def test_leere_tafel_ist_lesbar(self):
        leer = sc.parse(sc.rendere(sc.parse("")))
        self.assertEqual(leer["claims"], [])

    def test_kaputte_zeile_macht_die_tafel_nicht_unlesbar(self):
        # Eine von Hand verhunzte Zeile darf nicht die Koordination ALLER
        # Sitzungen ausfallen lassen.
        inhalt = sc.rendere({"claims": [
            {"item": "OUT-51", "sitzung": "B", "branch": "x",
             "seit": "2026-08-06T14:10Z", "dateien": "-"}],
            "blocker": [], "verlauf": []})
        inhalt += "| kaputt\n| | | |\n"
        tafel = sc.parse(inhalt)
        self.assertEqual([c["item"] for c in tafel["claims"]], ["OUT-51"])


class _TafelRepos(unittest.TestCase):
    """Bare-Repo + zwei Klone im Temp-Ordner — NIE die echte Tafel.

    Eigene Basis statt ``EchtesRennenTest`` zu erben: sonst liefen dessen
    Tests in jeder abgeleiteten Klasse ein zweites Mal.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lightos_claim_")
        self.bare = os.path.join(self.tmp, "origin.git")
        _git("init", "--quiet", "--bare", self.bare)
        self.a = self._klon("a")
        self.b = self._klon("b")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _klon(self, name):
        pfad = os.path.join(self.tmp, name)
        _git("clone", "--quiet", self.bare, pfad)
        _git("config", "user.email", "test@example.invalid", repo=pfad)
        _git("config", "user.name", "Test", repo=pfad)
        return pfad

    def _main(self, *argv):
        """``sc.main`` mit eingefangenem stdout/stderr -> (rc, out, err)."""
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = sc.main(list(argv))
        return rc, out.getvalue(), err.getvalue()


class PfadVergleichTest(unittest.TestCase):
    """PROC-16 — die reine Logik hinter der Ueberschneidungspruefung."""

    def test_trenner_und_schreibweise_sind_egal(self):
        self.assertTrue(sc.pfade_ueberlappen("src\\core\\x.py", "src/core/x.py"))
        self.assertTrue(sc.pfade_ueberlappen("./src//core/x.py", "src/core/x.py"))
        self.assertTrue(sc.pfade_ueberlappen("SRC/Core/X.py", "src/core/x.py"))

    def test_ordner_umfasst_seinen_inhalt_in_beide_richtungen(self):
        self.assertTrue(sc.pfade_ueberlappen("src/core/", "src/core/dmx/a.py"))
        self.assertTrue(sc.pfade_ueberlappen("src/core/dmx/a.py", "src\\core"))

    def test_praefix_nur_nach_ganzen_pfadteilen(self):
        """``src/core`` ist nicht ``src/core_alt.py`` — sonst warnt jede
        zweite Datei, und die Warnung wird uebergangen."""
        self.assertFalse(sc.pfade_ueberlappen("src/core", "src/core_alt.py"))
        self.assertFalse(sc.pfade_ueberlappen("src/a.py", "src/b.py"))

    def test_verfallener_claim_und_identisches_item_zaehlen_nicht(self):
        t = sc.jetzt()
        frisch = sc.stempel(t - timedelta(minutes=10))
        alt = sc.stempel(t - timedelta(hours=9))
        tafel = {"claims": [
            {"item": "X-1", "sitzung": "A", "branch": "a", "seit": frisch,
             "dateien": "src/x.py"},
            {"item": "X-2", "sitzung": "C", "branch": "c", "seit": alt,
             "dateien": "src/x.py"},
            {"item": "X-3", "sitzung": "B", "branch": "b", "seit": frisch,
             "dateien": "docs/y.md · src/x.py"},
        ], "blocker": [], "verlauf": []}
        treffer = sc.ueberschneidungen(tafel, "A", "X-9", ["src/x.py"], t)
        # X-1 gehoert derselben Sitzung A, ist aber ein ANDERES Item: zaehlt.
        self.assertEqual([(c["item"], d) for c, d in treffer],
                         [("X-1", ["src/x.py"]), ("X-3", ["src/x.py"])])
        # Das identische Item ueberschneidet sich nicht mit sich selbst.
        treffer = sc.ueberschneidungen(tafel, "A", "x-1", ["src/x.py"], t)
        self.assertEqual([c["item"] for c, _ in treffer], ["X-3"])


class UeberschneidungBeimClaimTest(_TafelRepos):
    """★ PROC-16: ``claim`` hat ``--files`` nur gespeichert, nie verglichen.

    Zwei Sitzungen konnten dieselbe Datei aus verschiedenen Items belegen, und
    das Werkzeug meldete beiden Erfolg ohne ein Wort — der Konflikt fiel erst
    beim Merge an (COORDINATION.md, Fall 4)."""

    def test_zwei_claims_auf_dieselbe_datei_warnen(self):
        self.assertEqual(self._main("--repo", self.a, "claim", "OUT-51",
                                    "--session", "A", "--files",
                                    "src/core/app_state.py")[0], 0)
        rc, out, err = self._main("--repo", self.b, "claim", "QA-50",
                                  "--session", "B", "--files",
                                  "src\\core\\app_state.py")
        self.assertEqual(rc, 0, "ohne --strikt nur warnen")
        self.assertIn("Dateiueberschneidung", err)
        self.assertIn("OUT-51", err)
        self.assertIn("src/core/app_state.py", err)
        # Ohne --strikt wird trotzdem belegt.
        items = {c["item"] for c in sc.lade_tafel(self.a)[0]["claims"]}
        self.assertEqual(items, {"OUT-51", "QA-50"})

    def test_strikt_belegt_nicht_und_endet_mit_2(self):
        self._main("--repo", self.a, "claim", "OUT-51", "--session", "A",
                   "--files", "src/core/")
        rc, out, err = self._main("--repo", self.b, "claim", "QA-50",
                                  "--session", "B", "--strikt", "--files",
                                  "src/core/dmx/output_manager.py")
        self.assertEqual(rc, 2)
        self.assertIn("OUT-51", err)
        items = {c["item"] for c in sc.lade_tafel(self.a)[0]["claims"]}
        self.assertEqual(items, {"OUT-51"}, "--strikt darf nicht schreiben")

    def test_verfallener_fremder_claim_zaehlt_nicht(self):
        self._main("--repo", self.a, "claim", "OUT-51", "--session", "A",
                   "--files", "src/x.py")
        tafel, eltern = sc.lade_tafel(self.a)
        tafel["claims"][0]["seit"] = sc.stempel(sc.jetzt() - timedelta(hours=9))
        sc.schreibe_tafel(self.a, tafel, eltern, "altern")
        rc, out, err = self._main("--repo", self.b, "claim", "QA-50",
                                  "--session", "B", "--strikt",
                                  "--files", "src/x.py")
        self.assertEqual(rc, 0)
        self.assertNotIn("Dateiueberschneidung", err)

    def test_eigenes_anderes_item_wird_als_hinweis_gemeldet(self):
        """★ Die leitende Sitzung laesst mehrere Worktree-Agenten parallel
        unter DERSELBEN Kennung arbeiten. Bis 2026-10-01 wurden eigene Claims
        komplett uebersprungen — der haeufigste reale Konflikt blieb stumm."""
        self._main("--repo", self.a, "claim", "OUT-51", "--session", "A",
                   "--files", "src/x.py")
        rc, out, err = self._main("--repo", self.a, "claim", "QA-50",
                                  "--session", "A", "--files", "src/x.py")
        self.assertEqual(rc, 0, "ohne --strikt nur Hinweis")
        self.assertIn("eigenes Item OUT-51", err)
        self.assertIn("src/x.py", err)
        self.assertNotIn("fremden Claims", err, "eigene Kategorie, nicht fremd")
        items = {c["item"] for c in sc.lade_tafel(self.a)[0]["claims"]}
        self.assertEqual(items, {"OUT-51", "QA-50"})

    def test_eigenes_anderes_item_zaehlt_bei_strikt(self):
        self._main("--repo", self.a, "claim", "OUT-51", "--session", "A",
                   "--files", "src/x.py")
        rc, out, err = self._main("--repo", self.a, "claim", "QA-50",
                                  "--session", "A", "--strikt",
                                  "--files", "src/x.py")
        self.assertEqual(rc, 2)
        self.assertIn("eigenes Item OUT-51", err)
        items = {c["item"] for c in sc.lade_tafel(self.a)[0]["claims"]}
        self.assertEqual(items, {"OUT-51"}, "--strikt darf nicht schreiben")

    def test_erneuter_claim_desselben_items_meldet_nichts(self):
        self._main("--repo", self.a, "claim", "OUT-51", "--session", "A",
                   "--files", "src/x.py")
        rc, out, err = self._main("--repo", self.a, "claim", "OUT-51",
                                  "--session", "A", "--strikt",
                                  "--files", "src/x.py")
        self.assertEqual(rc, 0)
        self.assertNotIn("Dateiueberschneidung", err)

    def test_ohne_files_wird_gewarnt_aber_belegt(self):
        for files in ([], ["--files", "-"]):
            item = f"QA-{len(files)}"
            rc, out, err = self._main("--repo", self.a, "claim", item,
                                      "--session", "A", *files)
            self.assertEqual(rc, 0, files)
            self.assertIn("ohne --files", err, files)

    def test_refresh_warnt_nicht_wegen_fehlender_files(self):
        self._main("--repo", self.a, "claim", "OUT-51", "--session", "A",
                   "--files", "src/x.py")
        rc, out, err = self._main("--repo", self.a, "refresh", "OUT-51",
                                  "--session", "A")
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")


class BriefeAnSitzungTest(unittest.TestCase):
    """PROC-17 — ``list --fuer X``: was seit X' letztem Eintrag an X ging."""

    BLOCKER = [
        "2026-09-28T08:00Z (A) AN B: alte Frage, laengst beantwortet",
        "2026-09-28T09:00Z (B) erledigt, danke",
        "2026-09-29T10:00Z (A) AN B: neue Frage zu `app_state.py`",
        "2026-09-29T11:00Z (C) AN A UND B: Rig ab 14 Uhr belegt",
        "2026-09-29T12:00Z (A) AN C: nur fuer C",
        "2026-09-29T13:00Z (C) AN A, B UND C: Gate bitte nur mit -j 2",
        "2026-09-29T14:00Z (A) Ein PLAN B ist kein Brief an B",
        "2026-09-29T15:00Z (C) AN ALLE: main ist rot",
    ]

    def test_nur_nach_dem_letzten_eigenen_eintrag(self):
        an_b = sc.blocker_fuer(self.BLOCKER, "B")
        self.assertEqual([b[:17] for b in an_b], [
            "2026-09-29T10:00Z", "2026-09-29T11:00Z",
            "2026-09-29T13:00Z", "2026-09-29T15:00Z"])

    def test_ohne_eigenen_eintrag_zaehlt_die_ganze_liste(self):
        an_d = sc.blocker_fuer(self.BLOCKER[:3], "D")
        self.assertEqual(an_d, [])
        an_b = sc.blocker_fuer(self.BLOCKER[:1], "b")
        self.assertEqual(len(an_b), 1, "Gross/klein der Sitzung egal")

    def test_ausgabe_von_list_fuer(self):
        import contextlib
        import io
        from types import SimpleNamespace
        alt = sc.lade_tafel
        sc.lade_tafel = lambda repo: (
            {"claims": [], "blocker": list(self.BLOCKER)}, None)
        try:
            puffer = io.StringIO()
            with contextlib.redirect_stdout(puffer):
                sc.cmd_list(SimpleNamespace(blocker=5, fuer="C"), "-")
        finally:
            sc.lade_tafel = alt
        aus = puffer.getvalue()
        # C schrieb zuletzt um 15:00 — danach kam nichts mehr an C.
        self.assertIn("Nichts an C", aus)
        self.assertNotIn("nur fuer C", aus)

    def test_text_aus_bytes_mit_windows_zeilenenden(self):
        roh = "AN B: Zeile eins\r\n  Zeile zwei mit `x` und Ümlaut\r\n\r\n".encode()
        self.assertEqual(sc.blocker_text(roh),
                         "AN B: Zeile eins Zeile zwei mit `x` und Ümlaut")

    def test_text_mit_bom_und_utf16(self):
        self.assertEqual(sc.blocker_text("﻿Ärger\r\n".encode("utf-8")), "Ärger")
        # Windows PowerShell 5: `> datei.txt` schreibt UTF-16LE mit BOM.
        self.assertEqual(sc.blocker_text("Ärger\r\n".encode("utf-16")), "Ärger")

    def test_kein_utf8_ist_ein_lauter_fehler(self):
        with self.assertRaises(UnicodeDecodeError):
            sc.blocker_text("Ärger".encode("cp1252"))


class BlockerAusStdinTest(_TafelRepos):
    """PROC-17 — ``blocker --datei -`` / ``--datei <pfad>`` gegen ein Temp-Repo.

    Hintergrund: als Shell-Argument wurden Backticks im Blocker-Text von der
    Shell AUSGEFUEHRT. Ueber stdin kommt der Text unveraendert an."""

    def _mit_stdin(self, roh, *argv):
        import io
        alt = sys.stdin
        sys.stdin = io.TextIOWrapper(io.BytesIO(roh), encoding="utf-8")
        try:
            return self._main(*argv)
        finally:
            sys.stdin = alt

    def test_stdin_mit_crlf_und_backticks(self):
        roh = "AN B: bitte `rm -rf` NICHT ausfuehren\r\nzweite Zeile — Ü\r\n".encode()
        rc, out, err = self._mit_stdin(roh, "--repo", self.a, "blocker",
                                       "--session", "A", "--datei", "-")
        self.assertEqual(rc, 0, err)
        tafel, _ = sc.lade_tafel(self.b)
        self.assertEqual(len(tafel["blocker"]), 1)
        self.assertTrue(tafel["blocker"][0].endswith(
            "(A) AN B: bitte `rm -rf` NICHT ausfuehren zweite Zeile — Ü"))
        self.assertNotIn("\r", tafel["blocker"][0])

    def test_datei_als_quelle(self):
        pfad = os.path.join(self.tmp, "brief.txt")
        with open(pfad, "wb") as f:
            f.write(b"AN B: aus der Datei\r\n")
        rc, out, err = self._main("--repo", self.a, "blocker", "--session",
                                  "A", "--datei", pfad)
        self.assertEqual(rc, 0, err)
        self.assertIn("aus der Datei", sc.lade_tafel(self.a)[0]["blocker"][0])

    def test_text_und_datei_zugleich_ist_ein_fehler(self):
        rc, out, err = self._main("--repo", self.a, "blocker", "x",
                                  "--session", "A", "--datei", "-")
        self.assertEqual(rc, 2)
        self.assertEqual(sc.lade_tafel(self.a)[0]["blocker"], [])

    def test_privates_aus_stdin_wird_ebenso_abgelehnt(self):
        roh = ("liegt unter " + "/home/" + "martin" + "/x").encode()
        rc, out, err = self._mit_stdin(roh, "--repo", self.a, "blocker",
                                       "--session", "A", "--datei", "-")
        self.assertEqual(rc, 2)

    def test_verlorene_umlaute_aus_stdin_werden_angemahnt(self):
        """Windows PowerShell 5.1 kodiert die Pipe nach ``$OutputEncoding``
        (US-ASCII): aus „für“ wird still „f?r“ — gueltiges UTF-8, die
        Dekodierung merkt nichts. Nur das Muster verraet es."""
        rc, out, err = self._mit_stdin(b"AN B: f?r die Gr??e bitte warten",
                                       "--repo", self.a, "blocker",
                                       "--session", "A", "--datei", "-")
        self.assertEqual(rc, 0, "nur Hinweis, geschrieben wird trotzdem")
        self.assertIn("verlorene Umlaute", err)
        self.assertIn("f?r", err)
        self.assertIn("--datei brief.txt", err)
        self.assertEqual(len(sc.lade_tafel(self.a)[0]["blocker"]), 1)

    def test_gewolltes_fragezeichen_bleibt_still(self):
        rc, out, err = self._mit_stdin("AN B: fertig? Ja — für 1?2 nicht"
                                       .encode(), "--repo", self.a, "blocker",
                                       "--session", "A", "--datei", "-")
        self.assertEqual(rc, 0, err)
        self.assertNotIn("Umlaute", err)

    def test_langer_text_wird_angemahnt_aber_geschrieben(self):
        rc, out, err = self._main("--repo", self.a, "blocker", "x" * 300,
                                  "--session", "A")
        self.assertEqual(rc, 0)
        self.assertIn("300 Zeichen", err)
        self.assertEqual(len(sc.lade_tafel(self.a)[0]["blocker"]), 1)
        rc, out, err = self._main("--repo", self.a, "blocker", "kurz",
                                  "--session", "A")
        self.assertNotIn("Zeichen", err)

    def test_list_fuer_ueber_die_echte_tafel(self):
        self._main("--repo", self.a, "blocker", "AN B: Frage eins", "--session", "A")
        self._main("--repo", self.b, "blocker", "gelesen", "--session", "B")
        self._main("--repo", self.a, "blocker", "AN A UND B: Frage zwei",
                   "--session", "C")
        rc, out, err = self._main("--repo", self.b, "list", "--fuer", "B")
        self.assertEqual(rc, 0)
        self.assertIn("Frage zwei", out)
        self.assertNotIn("Frage eins", out)


class VerfallTest(unittest.TestCase):
    def test_frischer_claim_gilt(self):
        t = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
        c = {"seit": sc.stempel(t - timedelta(hours=1))}
        self.assertFalse(sc.ist_verfallen(c, t))

    def test_alter_claim_verfaellt(self):
        t = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
        c = {"seit": sc.stempel(t - timedelta(hours=5))}
        self.assertTrue(sc.ist_verfallen(c, t))

    def test_unlesbarer_stempel_gilt_NICHT_als_verfallen(self):
        """★ Die gefaehrlichere Richtung bewusst gewaehlt.

        Einen Claim, den man nicht datieren kann, im Zweifel zu uebernehmen
        hiesse: zwei Sitzungen am selben Item. Ihn stehen zu lassen kostet
        hoechstens Wartezeit — und die faellt auf, der Doppelgriff nicht.
        """
        t = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
        self.assertFalse(sc.ist_verfallen({"seit": "gestern"}, t))
        self.assertFalse(sc.ist_verfallen({}, t))


# ★ Bewusst zusammengesetzt statt ausgeschrieben. Diese Datei prueft einen
# Waechter, der genau solche Pfade sucht — stuende das Beispiel woertlich hier,
# schlueg `tests/test_keine_privaten_dateien.py` an der Testdatei des eigenen
# Waechters an. (Genau so passiert, 2026-08-06: das Gate fand sich selbst.)
# Die Namen sind erfunden; es geht nur um die FORM des Pfades. Bewusst
# ZUSAMMENGESETZT und nicht hingeschrieben: der Waechter in
# tests/test_keine_privaten_dateien.py durchsucht `tests/` mit, und ein
# Literal hier waere fuer ihn nicht von einem echten Leck zu unterscheiden.
# PRIV-04: bis 2026-09-03 galt das nur fuer die Linux-Zeile — die Windows-Form
# stand als Literal da, weil sie gar nicht geprueft wurde.
_BEISPIEL_HOME = "/home/" + "martin"
_BEISPIEL_WIN = r"C:\Users" + "\\" + "Anna" + r"\lightos kaputt"


class OeffentlichkeitsPruefungTest(unittest.TestCase):
    """Die Tafel liegt auf GitHub — Blocker-Freitext ist die Leck-Stelle."""

    def test_faengt_private_angaben(self):
        self.assertTrue(sc.pruefe_oeffentlich(f"Show liegt in {_BEISPIEL_HOME}/shows"))
        self.assertTrue(sc.pruefe_oeffentlich(_BEISPIEL_WIN))
        self.assertTrue(sc.pruefe_oeffentlich("siehe claude.ai/code/session_abc"))
        self.assertTrue(sc.pruefe_oeffentlich("melde dich bei a.b@example.com"))

    def test_laesst_fachliches_durch(self):
        for text in ("Enttec auf /dev/ttyUSB0 haengt",
                     "Art-Net an 192.168.1.99 antwortet nicht",
                     "test_viz14_place_ghost_scene.py flakt (XPLAT-17)",
                     "Pfade bitte als /home/user/ schreiben"):
            self.assertEqual(sc.pruefe_oeffentlich(text), [], text)


# PRIV-05: Testname zusammengesetzt — ein echter Klarname steht nie im Repo.
_TESTNAME = "Kunig" + "unde"


class KlarnamenUndSchraegstrichTest(unittest.TestCase):
    """PRIV-05: Klarnamen aus einer LOKALEN Liste und ``C:/Users/<konto>/``."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.liste = os.path.join(self._tmp.name, "klarnamen.txt")
        with open(self.liste, "w", encoding="utf-8") as f:
            f.write("# Kommentar\n" + _TESTNAME + "\n\n")
        self._alt = os.environ.get("LIGHTOS_KLARNAMEN")
        os.environ["LIGHTOS_KLARNAMEN"] = self.liste

    def tearDown(self):
        if self._alt is None:
            os.environ.pop("LIGHTOS_KLARNAMEN", None)
        else:
            os.environ["LIGHTOS_KLARNAMEN"] = self._alt
        self._tmp.cleanup()

    def test_klarname_wird_gefunden_auch_genitiv_und_klein(self):
        for text in (f"{_TESTNAME} hat bestaetigt", f"auf {_TESTNAME}s Rig",
                     f"laut {_TESTNAME.lower()}"):
            self.assertTrue(sc.pruefe_oeffentlich(text), text)

    def test_meldung_verraet_den_namen_nicht(self):
        funde = sc.pruefe_oeffentlich(f"{_TESTNAME} war da")
        self.assertTrue(funde)
        self.assertNotIn(_TESTNAME, " ".join(funde))

    def test_wortteile_und_pseudonym_bleiben_frei(self):
        for text in (f"{_TESTNAME}nbaum ist kein Name", "Robin hat bestaetigt"):
            self.assertEqual(sc.pruefe_oeffentlich(text), [], text)

    def test_ohne_liste_keine_namenspruefung(self):
        os.environ["LIGHTOS_KLARNAMEN"] = os.path.join(self._tmp.name, "fehlt.txt")
        self.assertEqual(sc.pruefe_oeffentlich(f"{_TESTNAME} war da"), [])

    def test_windows_pfad_mit_schraegstrich(self):
        pfad = "C:/Users/" + "Anna" + "/lightos"
        self.assertTrue(sc.pruefe_oeffentlich(f"liegt in {pfad}"))
        self.assertEqual(sc.pruefe_oeffentlich("liegt in C:/Users/X/lightos"), [])

    def test_git_ordner_ist_zweiter_ort_und_nicht_versioniert(self):
        """Fuer Rechner ohne Schreibrecht ausserhalb des Projektordners: die
        Liste darf in <git-common-dir> liegen — dort wird nichts versioniert."""
        os.environ.pop("LIGHTOS_KLARNAMEN", None)
        ort = sc._git_klarnamen_datei()
        self.assertTrue(ort and ort.endswith("klarnamen.txt"), ort)
        common = subprocess.run(["git", "rev-parse", "--git-common-dir"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
        self.assertEqual(os.path.basename(os.path.dirname(ort)), os.path.basename(common))

    def test_liste_liegt_ausserhalb_des_repos(self):
        os.environ.pop("LIGHTOS_KLARNAMEN", None)
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ort = os.path.abspath(sc.klarnamen_datei())
        self.assertFalse(ort.startswith(repo + os.sep), ort)


class EchtesRennenTest(unittest.TestCase):
    """★★ Der Test, wegen dem es das Werkzeug gibt.

    Zwei Klone, beide sehen „frei", beide claimen dasselbe Item. Genau einer
    darf gewinnen — und der Verlierer muss es **merken**, nicht in dem Glauben
    weiterarbeiten, er haette das Item.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lightos_claim_")
        self.bare = os.path.join(self.tmp, "origin.git")
        _git("init", "--quiet", "--bare", self.bare)
        self.a = self._klon("a")
        self.b = self._klon("b")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _klon(self, name):
        pfad = os.path.join(self.tmp, name)
        _git("clone", "--quiet", self.bare, pfad)
        _git("config", "user.email", "test@example.invalid", repo=pfad)
        _git("config", "user.name", "Test", repo=pfad)
        return pfad

    def _claim(self, repo, item, sitzung):
        return sc.main(["--repo", repo, "claim", item, "--session", sitzung,
                        "--branch", f"fix/{item.lower()}"])

    def test_genau_einer_gewinnt(self):
        # Beide lesen den (leeren) Stand, bevor einer schreibt — das ist die
        # Gleichzeitigkeit, um die es geht.
        tafel_a, eltern_a = sc.lade_tafel(self.a)
        tafel_b, eltern_b = sc.lade_tafel(self.b)
        self.assertEqual(eltern_a, eltern_b)

        tafel_a["claims"].append({"item": "OUT-51", "sitzung": "A",
                                  "branch": "x", "seit": sc.stempel(sc.jetzt()),
                                  "dateien": "-"})
        tafel_b["claims"].append({"item": "OUT-51", "sitzung": "B",
                                  "branch": "y", "seit": sc.stempel(sc.jetzt()),
                                  "dateien": "-"})

        self.assertTrue(sc.schreibe_tafel(self.a, tafel_a, eltern_a, "A"))
        # ★ B schreibt gegen den Stand, den es GELESEN hat — der ist nicht mehr
        # die Spitze. Git lehnt ab; genau daran erkennt B das verlorene Rennen.
        self.assertFalse(sc.schreibe_tafel(self.b, tafel_b, eltern_b, "B"))

        endstand, _ = sc.lade_tafel(self.b)
        self.assertEqual([c["sitzung"] for c in endstand["claims"]], ["A"])

    def test_verlierer_bekommt_belegt_gemeldet(self):
        self.assertEqual(self._claim(self.a, "OUT-51", "A"), 0)
        # B kennt A's Claim noch nicht — bis `claim` selbst fetcht.
        self.assertEqual(self._claim(self.b, "OUT-51", "B"), 1,
                         "B haette das Item sonst fuer sich reklamiert")
        tafel, _ = sc.lade_tafel(self.b)
        self.assertEqual(len(tafel["claims"]), 1)
        self.assertEqual(tafel["claims"][0]["sitzung"], "A")

    def test_verschiedene_items_stoeren_sich_nicht(self):
        self.assertEqual(self._claim(self.a, "OUT-51", "A"), 0)
        self.assertEqual(self._claim(self.b, "QA-50", "B"), 0)
        tafel, _ = sc.lade_tafel(self.a)
        self.assertEqual({c["item"]: c["sitzung"] for c in tafel["claims"]},
                         {"OUT-51": "A", "QA-50": "B"})

    def test_freigeben_macht_das_item_wieder_belegbar(self):
        self._claim(self.a, "OUT-51", "A")
        self.assertEqual(sc.main(["--repo", self.a, "release", "OUT-51",
                                  "--session", "A", "--status", "done"]), 0)
        self.assertEqual(self._claim(self.b, "OUT-51", "B"), 0)

    def test_fremdes_item_nicht_versehentlich_freigeben(self):
        self._claim(self.a, "OUT-51", "A")
        self.assertEqual(sc.main(["--repo", self.b, "release", "OUT-51",
                                  "--session", "B"]), 1,
                         "B darf A's Item nicht ohne --force freigeben")

    def test_eigener_claim_laesst_sich_auffrischen(self):
        self._claim(self.a, "OUT-51", "A")
        self.assertEqual(sc.main(["--repo", self.a, "refresh", "OUT-51",
                                  "--session", "A"]), 0)
        tafel, _ = sc.lade_tafel(self.a)
        self.assertEqual(len(tafel["claims"]), 1)

    def test_umbelegen_traegt_zweig_und_dateien_nach(self):
        """★★★ PROC-12, GEMESSEN IM ECHTEN BETRIEB: ein erneuter ``claim``
        derselben Sitzung hat nur den Zeitstempel angefasst und ``--branch``
        sowie ``--files`` STILL VERWORFEN — und dabei „Claim aufgefrischt"
        gemeldet, also Erfolg.

        Was daraus wurde: A hat FM-41 zweimal mit neuem Zweig und neuer
        Dateiliste belegt; die Tafel zeigte weiterhin den ERSTEN Zweig und EINE
        Datei. B las daraus, A fasse ``app_state.py`` nicht an, und nahm sich
        ein Item, das genau dort arbeitet. **Die Tafel verschwieg eine
        Ueberschneidung, statt sie zu nennen** — die einzige Fehlrichtung, die
        dieses Werkzeug nicht haben darf, denn es existiert genau dafuer.
        """
        self._claim(self.a, "OUT-51", "A")
        rc = sc.main(["--repo", self.a, "claim", "OUT-51", "--session", "A",
                      "--branch", "feature/zweiter-zweig",
                      "--files", "src/x.py", "src/y.py"])
        self.assertEqual(rc, 0)
        tafel, _ = sc.lade_tafel(self.a)
        self.assertEqual(len(tafel["claims"]), 1, "kein zweiter Eintrag")
        eintrag = tafel["claims"][0]
        self.assertEqual(eintrag["branch"], "feature/zweiter-zweig")
        self.assertIn("src/x.py", eintrag["dateien"])
        self.assertIn("src/y.py", eintrag["dateien"])

    def test_umbelegen_steht_im_verlauf(self):
        """Die andere Sitzung muss die Aenderung SEHEN koennen, nicht nur den
        neuen Endzustand — sonst merkt niemand, dass sich der Zuschnitt
        verschoben hat."""
        self._claim(self.a, "OUT-51", "A")
        sc.main(["--repo", self.a, "claim", "OUT-51", "--session", "A",
                 "--branch", "feature/zweiter-zweig", "--files", "src/x.py"])
        tafel, _ = sc.lade_tafel(self.a)
        verlauf = " ".join(tafel["verlauf"])
        self.assertIn("aktualisiert OUT-51", verlauf)
        self.assertIn("feature/zweiter-zweig", verlauf)

    def test_refresh_bleibt_ein_reines_auffrischen(self):
        """★ Die Gegenprobe, und sie ist der Grund fuer die Bedingung
        ``args.files is not None``: ``refresh`` reicht bewusst ``None`` durch
        und darf den Zuschnitt NICHT loeschen. Ohne diese Abgrenzung haette
        der Fix aus einem stillen Verschweigen ein stilles Vergessen gemacht."""
        sc.main(["--repo", self.a, "claim", "OUT-51", "--session", "A",
                 "--branch", "fix/eins", "--files", "src/x.py"])
        sc.main(["--repo", self.a, "refresh", "OUT-51", "--session", "A"])
        eintrag = sc.lade_tafel(self.a)[0]["claims"][0]
        self.assertEqual(eintrag["branch"], "fix/eins")
        self.assertIn("src/x.py", eintrag["dateien"])

    def test_verfallener_claim_wird_uebernommen_und_protokolliert(self):
        self._claim(self.a, "OUT-51", "A")
        # Claim kuenstlich altern lassen.
        tafel, eltern = sc.lade_tafel(self.a)
        tafel["claims"][0]["seit"] = sc.stempel(sc.jetzt() - timedelta(hours=9))
        sc.schreibe_tafel(self.a, tafel, eltern, "altern")

        self.assertEqual(self._claim(self.b, "OUT-51", "B"), 0)
        tafel, _ = sc.lade_tafel(self.b)
        self.assertEqual(tafel["claims"][0]["sitzung"], "B")
        self.assertTrue(any("uebernimmt OUT-51" in v for v in tafel["verlauf"]),
                        "eine Uebernahme muss nachvollziehbar bleiben")

    def test_blocker_mit_privatem_pfad_wird_abgelehnt(self):
        self.assertEqual(sc.main(["--repo", self.a, "blocker",
                                  f"kaputt: {_BEISPIEL_HOME}/shows/x.lshow",
                                  "--session", "A"]), 2)
        tafel, _ = sc.lade_tafel(self.a)
        self.assertEqual(tafel["blocker"], [])

    def test_blocker_landet_fuer_die_andere_sitzung_sichtbar(self):
        self.assertEqual(sc.main(["--repo", self.a, "blocker",
                                  "Rig laeuft — App nicht neu starten",
                                  "--session", "A"]), 0)
        tafel, _ = sc.lade_tafel(self.b)
        self.assertEqual(len(tafel["blocker"]), 1)
        self.assertIn("Rig laeuft", tafel["blocker"][0])

    def test_arbeitsbaum_bleibt_unberuehrt(self):
        """★ Ein Claim darf der anderen Sitzung nicht in den Worktree greifen.

        Deshalb Plumbing statt Checkout: kein Branch-Wechsel, keine Datei im
        Arbeitsbaum, kein Eingriff in laufende Arbeit.
        """
        _git("commit", "--quiet", "--allow-empty", "-m", "start", repo=self.a)
        vorher_status = _git("status", "--porcelain", repo=self.a)
        vorher_branch = _git("rev-parse", "--abbrev-ref", "HEAD", repo=self.a)
        self._claim(self.a, "OUT-51", "A")
        self.assertEqual(_git("status", "--porcelain", repo=self.a), vorher_status)
        self.assertEqual(_git("rev-parse", "--abbrev-ref", "HEAD", repo=self.a),
                         vorher_branch)
        self.assertFalse(os.path.exists(os.path.join(self.a, sc.DATEI)))


if __name__ == "__main__":
    unittest.main()
