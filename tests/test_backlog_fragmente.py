"""PROC-20: BACKLOG-Fragmente unter ``backlog.d/`` statt Konflikten in BACKLOG.md.

Jeder Feature-PR aenderte bisher ``BACKLOG.md`` (neue Zeile bzw. Status
``review (Zweig …)``). Nach JEDEM Merge kollidierten deshalb die naechsten PRs
in derselben Datei, und gemergte Items blieben auf ``review`` stehen. Jetzt
bringt ein PR je Item eine Datei ``backlog.d/<ID>.md`` mit;
``tools/backlog_sammeln.py`` traegt sie nach dem Merge in ``BACKLOG.md`` ein.

Geprueft wird:

1. **Form** — Kopfzeilen, Dateiname = ID, kaputte Fragmente, doppelte ID.
2. **Sammeln** — neue Zeile an der Gruppenstelle, Statusspalte ersetzen,
   ``review`` wird mit PR-Nummer zu ``done``, idempotent, ``--pruefen`` und
   ``--dry-run`` schreiben nichts, Zeilenenden bleiben.
3. **PR-Nummer aus der Historie** — echtes Wegwerf-Repo.
4. **Waechter** — eine direkte Aenderung an BACKLOG.md wird GEMELDET, macht
   aber nichts rot (Uebergang: offene PRs alter Art bleiben gueltig).
5. **Der echte Baum** — Fragmente wohlgeformt, Sammellauf waere moeglich,
   Fragment zaehlt fuer Gates wie eine BACKLOG-Zeile, Doku nennt den Ablauf.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))


def _modul(name: str):
    spec = importlib.util.spec_from_file_location(
        f"_{name}_unter_test", REPO / "tools" / f"{name}.py")
    assert spec and spec.loader, f"{name}.py nicht ladbar"
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bs = _modul("backlog_sammeln")

BACKLOG = (
    "# Backlog\n\nText.\n\n"
    "| ID | Prio | Status | Titel | Details |\n|---|---|---|---|---|\n"
    "| FM-1 | P2 | done | **Alt** | x |\n"
    "| PROC-18 | P1 | ✅ done (2026-10-02) | **Lizenzen** | y |\n"
    "| FM-2 | P3 | todo | **Offen** | z |\n"
    "\nZwischentext.\n\n"
    "| ID | Prio | Status | Item |\n|---|---|---|---|\n"
    "| QA-7 | P2 | review (Zweig `feature/qa7`) | **Vier Spalten** Text. |\n"
)


def _neu(id_: str, status: str = "todo", prio: str = "P2",
         titel: str = "Ein Titel", details: str = "Ein Satz dazu.",
         extra: str = "") -> str:
    return (f"ID: {id_}\nPrioritaet: {prio}\nStatus: {status}\n"
            f"Titel: {titel}\n{extra}\n{details}\n")


def _still(*_a, **_k):
    pass


class FragmentFormTest(unittest.TestCase):

    def test_gueltiges_fragment(self):
        f, fehler = bs.lies_fragment("PROC-20.md", _neu("PROC-20", "review"))
        self.assertEqual(fehler, [])
        self.assertEqual((f.id, f.prio, f.status, f.titel, f.details),
                         ("PROC-20", "P2", "review", "Ein Titel", "Ein Satz dazu."))

    def test_nur_status_genuegt_fuer_ein_vorhandenes_item(self):
        f, fehler = bs.lies_fragment(
            "FM-2.md", "ID: FM-2\nStatus: teils\nStatus-Notiz: Teil 1 geliefert\n")
        self.assertEqual(fehler, [])
        self.assertEqual((f.status, f.notiz, f.titel), ("teils", "Teil 1 geliefert", ""))

    def test_formfehler_werden_gemeldet(self):
        faelle = {
            "leer": ("FM-3.md", "\n"),
            "ohne Status": ("FM-3.md", "ID: FM-3\nTitel: T\n"),
            "unbekannter Status": ("FM-3.md", "ID: FM-3\nStatus: fertig\n"),
            "ID passt nicht zum Namen": ("FM-3.md", "ID: FM-4\nStatus: todo\n"),
            "Dateiname ist keine ID": ("notiz.md", "ID: notiz\nStatus: todo\n"),
            "unbekannte Kopfzeile": ("FM-3.md", "ID: FM-3\nStatus: todo\nFarbe: rot\n"),
            "doppelte Kopfzeile": ("FM-3.md", "ID: FM-3\nStatus: todo\nStatus: done\n"),
            "falsche Prioritaet": ("FM-3.md", "ID: FM-3\nPrioritaet: hoch\nStatus: todo\n"),
            "Tabellenstrich": ("FM-3.md", _neu("FM-3", details="a | b")),
            "Strich im Titel": ("FM-3.md", _neu("FM-3", titel="a | b")),
        }
        for was, (name, text) in faelle.items():
            _f, fehler = bs.lies_fragment(name, text)
            self.assertTrue(fehler, f"nicht gemeldet: {was}")

    def test_readme_ist_kein_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "backlog.d").mkdir()
            (repo / "backlog.d" / "README.md").write_text("# x\n", encoding="utf-8")
            self.assertEqual(bs.fragmente(repo), [])


class _Tmp(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        (self.repo / "backlog.d").mkdir()
        (self.repo / "BACKLOG.md").write_bytes(BACKLOG.encode("utf-8"))

    def frag(self, name: str, text: str):
        (self.repo / "backlog.d" / name).write_text(text, encoding="utf-8")

    def backlog(self) -> str:
        return (self.repo / "BACKLOG.md").read_text(encoding="utf-8")

    def zeile(self, id_: str) -> str:
        treffer = [z for z in self.backlog().split("\n") if z.startswith(f"| {id_} |")]
        self.assertEqual(len(treffer), 1, f"{id_}: {treffer}")
        return treffer[0]

    def reste(self) -> list[str]:
        return sorted(p.name for p in (self.repo / "backlog.d").iterdir())


class SammelnTest(_Tmp):

    def test_neues_item_landet_hinter_der_hoechsten_nummer_seiner_gruppe(self):
        self.frag("PROC-20.md", _neu("PROC-20", titel="Fragmente", details="Zeile 1\nZeile 2"))
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        zeilen = self.backlog().split("\n")
        i = next(n for n, z in enumerate(zeilen) if z.startswith("| PROC-18 |"))
        self.assertEqual(zeilen[i + 1],
                         "| PROC-20 | P2 | todo | **Fragmente** | Zeile 1 Zeile 2 |")
        self.assertEqual(zeilen[i + 2][:8], "| FM-2 |", "Nachbarzeile verrutscht")
        self.assertEqual(self.reste(), [], "Fragment muss nach dem Sammeln weg sein")

    def test_tabelle_mit_vier_spalten_bekommt_vier_spalten(self):
        self.frag("QA-8.md", _neu("QA-8", titel="Neu", details="Text."))
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        self.assertEqual(self.zeile("QA-8"), "| QA-8 | P2 | todo | **Neu** Text. |")

    def test_mehrere_neue_derselben_gruppe_in_nummernfolge(self):
        self.frag("FM-11.md", _neu("FM-11"))
        self.frag("FM-9.md", _neu("FM-9"))
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        ids = [z.split("|")[1].strip() for z in self.backlog().split("\n")
               if z.startswith("| FM-")]
        self.assertEqual(ids, ["FM-1", "FM-2", "FM-9", "FM-11"])

    def test_neue_gruppe_braucht_nach(self):
        self.frag("NEU-1.md", _neu("NEU-1"))
        vorher = self.backlog()
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 1)
        self.assertEqual(self.backlog(), vorher)
        self.frag("NEU-1.md", _neu("NEU-1", extra="Nach: FM-1\n"))
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        zeilen = self.backlog().split("\n")
        i = next(n for n, z in enumerate(zeilen) if z.startswith("| FM-1 |"))
        self.assertTrue(zeilen[i + 1].startswith("| NEU-1 | P2 | todo |"))

    def test_neues_item_ohne_titel_oder_prioritaet_ist_ein_fehler(self):
        self.frag("FM-3.md", "ID: FM-3\nStatus: todo\n")
        vorher = self.backlog()
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 1)
        self.assertEqual(self.backlog(), vorher)
        self.assertEqual(self.reste(), ["FM-3.md"])

    def test_wartendes_review_fragment_wird_trotzdem_geprueft(self):
        """Im PR hat ein 'review'-Fragment noch keine PR-Nummer. Sein Fehler
        muss trotzdem DORT auffallen, nicht erst beim Sammeln auf main."""
        self.frag("FM-3.md", "ID: FM-3\nStatus: review\n")
        self.assertEqual(bs.sammeln(self.repo, pruefen=True, ausgabe=_still), 1)
        self.frag("FM-3.md", _neu("FM-3", "review"))
        self.assertEqual(bs.sammeln(self.repo, pruefen=True, ausgabe=_still), 0)

    def test_neues_item_hinter_einem_noch_wartenden_bleibt_mit_liegen(self):
        self.frag("NEU-1.md", _neu("NEU-1", "review", extra="Nach: FM-1\n"))
        self.frag("NEU-2.md", _neu("NEU-2", "todo"))
        vorher = self.backlog()
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        self.assertEqual(self.backlog(), vorher)
        self.assertEqual(self.reste(), ["NEU-1.md", "NEU-2.md"])
        self.assertEqual(bs.sammeln(self.repo, pr=4, heute="2026-10-10", ausgabe=_still), 0)
        ids = [z.split("|")[1].strip() for z in self.backlog().split("\n")
               if z.startswith(("| FM-", "| NEU-"))]
        self.assertEqual(ids, ["FM-1", "NEU-1", "NEU-2", "FM-2"])
        self.assertEqual(self.reste(), [])

    def test_status_eines_vorhandenen_items_wird_ersetzt_sonst_nichts(self):
        self.frag("FM-2.md", "ID: FM-2\nStatus: teils\nStatus-Notiz: Teil 1 geliefert\n")
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        self.assertEqual(self.zeile("FM-2"),
                         "| FM-2 | P3 | teils — Teil 1 geliefert | **Offen** | z |")
        self.assertEqual(self.backlog().replace(
            "teils — Teil 1 geliefert", "todo"), BACKLOG)

    def test_freitext_zu_vorhandener_zeile_faellt_nicht_still_weg(self):
        """Review-Fund: bei einer vorhandenen Zeile zaehlt nur der Status. Der
        Freitext des Fragments verschwindet mit der Datei — das muss der Lauf
        (auch --dry-run) sagen, sonst geht er unbemerkt verloren."""
        self.frag("FM-2.md", "ID: FM-2\nStatus: teils\n\nGeliefert: Teil 1.\n")
        for dry in (True, False):
            aus: list[str] = []
            self.assertEqual(bs.sammeln(self.repo, dry_run=dry, ausgabe=aus.append), 0)
            hinweise = [z for z in aus if "Hinweis FM-2" in z]
            self.assertEqual(len(hinweise), 1, aus)
            self.assertIn("NICHT uebernommen", hinweise[0])
        self.assertNotIn("Geliefert: Teil 1.", self.backlog())
        # Ohne Freitext kein Hinweis.
        self.frag("FM-2.md", "ID: FM-2\nStatus: todo\n")
        aus = []
        self.assertEqual(bs.sammeln(self.repo, ausgabe=aus.append), 0)
        self.assertFalse([z for z in aus if "Hinweis" in z], aus)

    def test_review_wird_mit_pr_nummer_zu_done(self):
        self.frag("QA-7.md", "ID: QA-7\nStatus: review\n")
        self.assertEqual(bs.sammeln(self.repo, pr=993, heute="2026-10-10",
                                    ausgabe=_still), 0)
        self.assertEqual(
            self.zeile("QA-7"),
            "| QA-7 | P2 | done (2026-10-10, [PR #993]"
            "(https://github.com/ixamgames-droid/lightos/pull/993)) "
            "| **Vier Spalten** Text. |")
        self.assertEqual(self.reste(), [])

    def test_review_ohne_pr_nummer_bleibt_liegen(self):
        """Ohne gemergten PR gibt es nichts abzuschliessen: das Fragment bleibt
        liegen, statt als ``review`` einzurasten (der alte Schaden)."""
        self.frag("QA-7.md", "ID: QA-7\nStatus: review\n")
        self.frag("FM-2.md", "ID: FM-2\nStatus: blocked\n")
        vorher_qa = self.zeile("QA-7")
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        self.assertEqual(self.zeile("QA-7"), vorher_qa)
        self.assertIn("| blocked |", self.zeile("FM-2"))
        self.assertEqual(self.reste(), ["QA-7.md"])

    def test_idempotent(self):
        self.frag("PROC-20.md", _neu("PROC-20", "review"))
        self.frag("FM-2.md", "ID: FM-2\nStatus: done\n")
        self.assertEqual(bs.sammeln(self.repo, pr=5, heute="2026-10-10", ausgabe=_still), 0)
        einmal = (self.repo / "BACKLOG.md").read_bytes()
        self.assertEqual(bs.sammeln(self.repo, pr=5, heute="2026-10-10", ausgabe=_still), 0)
        self.assertEqual((self.repo / "BACKLOG.md").read_bytes(), einmal)
        # Auch ein wieder aufgetauchtes Fragment (z. B. nach einem Merge)
        # verdoppelt nichts: die ID steht schon da, es bleibt eine Zeile.
        self.frag("PROC-20.md", _neu("PROC-20", "review"))
        self.assertEqual(bs.sammeln(self.repo, pr=5, heute="2026-10-10", ausgabe=_still), 0)
        self.assertEqual((self.repo / "BACKLOG.md").read_bytes(), einmal)

    def test_pruefen_und_dry_run_schreiben_nichts(self):
        self.frag("PROC-20.md", _neu("PROC-20"))
        vorher = (self.repo / "BACKLOG.md").read_bytes()
        gesagt: list[str] = []
        self.assertEqual(bs.sammeln(self.repo, pruefen=True, ausgabe=_still), 0)
        self.assertEqual(bs.sammeln(self.repo, dry_run=True, ausgabe=gesagt.append), 0)
        self.assertEqual((self.repo / "BACKLOG.md").read_bytes(), vorher)
        self.assertEqual(self.reste(), ["PROC-20.md"])
        self.assertTrue(any("| PROC-20 | P2 | todo |" in z for z in gesagt),
                        "--dry-run muss die Zeile zeigen, die es schreiben wuerde")

    def test_kaputtes_fragment_blockiert_alles(self):
        self.frag("PROC-20.md", _neu("PROC-20"))
        self.frag("FM-2.md", "ID: FM-2\nStatus: fertig\n")
        vorher = (self.repo / "BACKLOG.md").read_bytes()
        for kw in ({}, {"pruefen": True}, {"dry_run": True}):
            self.assertEqual(bs.sammeln(self.repo, ausgabe=_still, **kw), 1, kw)
        self.assertEqual((self.repo / "BACKLOG.md").read_bytes(), vorher)
        self.assertEqual(self.reste(), ["FM-2.md", "PROC-20.md"])

    def test_zwei_fragmente_gleicher_id_blockieren(self):
        self.frag("FM-2.md", "ID: FM-2\nStatus: done\n")
        self.frag("FM-2b.md", "ID: FM-2\nStatus: todo\n")
        gesagt: list[str] = []
        self.assertEqual(bs.sammeln(self.repo, pruefen=True, ausgabe=gesagt.append), 1)
        # Die Ursache muss beim Namen genannt sein — "ID passt nicht zum
        # Dateinamen" allein sagt nicht, dass es das Item schon gibt.
        self.assertTrue(any("zwei Fragmente fuer FM-2" in z and "FM-2.md" in z
                            and "FM-2b.md" in z for z in gesagt), gesagt)
        vorher = (self.repo / "BACKLOG.md").read_bytes()
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 1)
        self.assertEqual((self.repo / "BACKLOG.md").read_bytes(), vorher)

    def test_fremde_datei_wird_nicht_still_vergessen(self):
        (self.repo / "backlog.d" / "PROC-20.txt").write_text("x", encoding="utf-8")
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 1)

    def test_crlf_bleibt_crlf(self):
        (self.repo / "BACKLOG.md").write_bytes(BACKLOG.replace("\n", "\r\n").encode("utf-8"))
        (self.repo / "backlog.d" / "PROC-20.md").write_bytes(
            _neu("PROC-20").replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        roh = (self.repo / "BACKLOG.md").read_bytes()
        self.assertNotIn(b"\r\r", roh)
        self.assertEqual(roh.count(b"\n"), roh.count(b"\r\n"), "gemischte Zeilenenden")
        self.assertIn(b"| PROC-20 | P2 | todo |", roh)

    def test_ohne_fragmente_nichts_zu_tun(self):
        vorher = (self.repo / "BACKLOG.md").read_bytes()
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        self.assertEqual((self.repo / "BACKLOG.md").read_bytes(), vorher)

    def test_bekannte_ids_zaehlt_fragmente_wie_backlog_zeilen(self):
        """Der Baustein fuer jedes Gate, das „dieses Item gibt es" wissen will."""
        self.assertNotIn("PROC-20", bs.bekannte_ids(self.repo))
        self.frag("PROC-20.md", _neu("PROC-20"))
        ids = bs.bekannte_ids(self.repo)
        self.assertIn("PROC-20", ids)     # nur als Fragment
        self.assertIn("FM-2", ids)        # nur als BACKLOG-Zeile


class _GitRepo(_Tmp):
    """Wegwerf-Repo mit einem kuenstlichen ``origin/main``."""

    def setUp(self):
        super().setUp()
        self.env = dict(os.environ, GIT_AUTHOR_NAME="Test",
                        GIT_AUTHOR_EMAIL="t@example.invalid",
                        GIT_COMMITTER_NAME="Test",
                        GIT_COMMITTER_EMAIL="t@example.invalid")
        self.git("init", "-q", "-b", "main")
        self.git("config", "core.autocrlf", "false")
        self.commit("start")

    def git(self, *args, datum: str | None = None) -> str:
        env = dict(self.env)
        if datum:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = datum
        p = subprocess.run(("git", *args), cwd=self.repo, capture_output=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        return p.stdout.decode("utf-8").strip()

    def commit(self, betreff: str, datum: str | None = None):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", betreff, datum=datum)

    def main_hier_festhalten(self):
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")


class PrAusHistorieTest(_GitRepo):

    def test_squash_betreff_liefert_nummer_und_datum(self):
        self.frag("QA-7.md", "ID: QA-7\nStatus: review\n")
        self.commit("fix(qa): vier Spalten (QA-7) (#812)", datum="2026-10-09T12:00:00+0000")
        self.assertEqual(bs.pr_aus_git(self.repo, "backlog.d/QA-7.md"),
                         (812, "2026-10-09"))
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        self.assertIn("| done (2026-10-09, [PR #812](", self.zeile("QA-7"))
        self.assertEqual(self.reste(), [])

    def test_commit_ohne_pr_nummer_schliesst_nichts_ab(self):
        self.frag("QA-7.md", "ID: QA-7\nStatus: review\n")
        self.commit("fix(qa): vier Spalten (QA-7)")
        self.assertEqual(bs.pr_aus_git(self.repo, "backlog.d/QA-7.md"), (None, None))
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        self.assertIn("review (Zweig", self.zeile("QA-7"))
        self.assertEqual(self.reste(), ["QA-7.md"])

    def test_nicht_committetes_fragment_hat_keine_nummer(self):
        self.commit("etwas anderes (#7)")
        self.frag("QA-7.md", "ID: QA-7\nStatus: review\n")
        self.assertEqual(bs.pr_aus_git(self.repo, "backlog.d/QA-7.md"), (None, None))


    def test_nach_dem_merge_geaendertes_fragment_hat_keine_nummer(self):
        """Review-Fund: das Fragment kam mit (#812) nach main und wurde danach
        lokal geaendert (nicht committet). Die alte Nummer gilt fuer DIESEN
        Inhalt nicht — sonst wuerde ein neuer 'review'-Stand als 'done (#812)'
        eingetragen."""
        self.frag("QA-7.md", "ID: QA-7\nStatus: todo\n")
        self.commit("docs: Befund (QA-7) (#812)")
        self.assertEqual(bs.pr_aus_git(self.repo, "backlog.d/QA-7.md")[0], 812)
        self.frag("QA-7.md", "ID: QA-7\nStatus: review\n")
        self.assertEqual(bs.pr_aus_git(self.repo, "backlog.d/QA-7.md"), (None, None))
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        self.assertEqual(self.reste(), ["QA-7.md"])


class WaechterTest(_GitRepo):
    """Uebergang: BACKLOG.md direkt anzufassen wird gemeldet, nie rot."""

    def _hand(self):
        p = self.repo / "BACKLOG.md"
        p.write_text(p.read_text(encoding="utf-8").replace(
            "| todo | **Offen**", "| review (Zweig `x`) | **Offen**"), encoding="utf-8")

    def test_ohne_origin_main_still(self):
        self._hand()
        self.assertEqual(bs.direkte_aenderung(self.repo), "")

    def test_ausserhalb_von_git_still(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(bs.direkte_aenderung(Path(tmp)), "")

    def test_unveraendert_keine_meldung(self):
        self.main_hier_festhalten()
        self.assertEqual(bs.direkte_aenderung(self.repo), "")

    def test_hand_aenderung_wird_gemeldet_committet_und_uncommittet(self):
        self.main_hier_festhalten()
        self._hand()
        self.assertIn("BACKLOG.md", bs.direkte_aenderung(self.repo))
        self.commit("feat: mit Backlog")
        self.assertIn("backlog.d/", bs.direkte_aenderung(self.repo))

    def test_die_meldung_macht_nichts_rot(self):
        self.main_hier_festhalten()
        self._hand()
        self.commit("feat: mit Backlog")
        p = subprocess.run(
            (sys.executable, str(REPO / "tools" / "backlog_sammeln.py"),
             "--waechter", "--repo", str(self.repo)),
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("HINWEIS", p.stdout)

    def test_sammel_lauf_ist_keine_meldung(self):
        self.frag("FM-2.md", "ID: FM-2\nStatus: done\n")
        self.commit("feat: x (#3)")
        self.main_hier_festhalten()
        self.assertEqual(bs.sammeln(self.repo, ausgabe=_still), 0)
        self.commit("backlog: sammeln")
        self.assertEqual(bs.direkte_aenderung(self.repo), "")

    def test_zweig_hinter_main_bekommt_main_nicht_angelastet(self):
        self.git("checkout", "-q", "-b", "feature")
        (self.repo / "x.txt").write_text("x", encoding="utf-8")
        self.commit("feat: x")
        self.git("checkout", "-q", "main")
        self._hand()
        self.commit("backlog auf main")
        self.main_hier_festhalten()
        self.git("checkout", "-q", "feature")
        self.assertEqual(bs.direkte_aenderung(self.repo), "")


class EchterBaumTest(unittest.TestCase):

    def test_fragmente_sind_wohlgeformt_und_sammelbar(self):
        gesagt: list[str] = []
        rc = bs.sammeln(REPO, pruefen=True, ausgabe=gesagt.append)
        self.assertEqual(rc, 0, "backlog.d/ enthaelt ein kaputtes Fragment:\n"
                         + "\n".join(gesagt))

    def test_dieses_item_liegt_als_fragment_oder_zeile_vor(self):
        self.assertIn("PROC-20", bs.bekannte_ids(REPO))

    def test_direkte_backlog_aenderung_warnt_nur(self):
        """★ Bewusst KEIN assert: offene PRs alter Art (mit BACKLOG-Zeile)
        bleiben gueltig, und der Sammel-PR der leitenden Sitzung aendert
        BACKLOG.md absichtlich."""
        hinweis = bs.direkte_aenderung(REPO)
        if hinweis:
            warnings.warn(hinweis, stacklevel=1)

    def test_ablauf_steht_in_der_doku(self):
        for name in ("AGENTS.md", "WORKFLOW.md", "COORDINATION.md", "CONTRIBUTING.md"):
            text = (REPO / name).read_text(encoding="utf-8")
            self.assertIn("backlog.d/", text, name)
            self.assertIn("backlog_sammeln.py", text, name)
        self.assertTrue((REPO / "backlog.d" / "README.md").is_file())

    def test_werkzeug_steht_im_werkzeugverzeichnis(self):
        self.assertIn("backlog_sammeln.py",
                      (REPO / "tools" / "README.md").read_text(encoding="utf-8"))


class FragmentLinksTest(unittest.TestCase):
    """Fragment-Links gelten ab dem Repo-Wurzelverzeichnis (wie in BACKLOG.md)."""

    def test_links_werden_von_der_wurzel_aus_aufgeloest(self):
        cdl = _modul("check_doc_links")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "docs"))
            os.makedirs(os.path.join(tmp, "backlog.d"))
            with open(os.path.join(tmp, "docs", "ziel.md"), "w", encoding="utf-8") as f:
                f.write("# Ziel\n")
            with open(os.path.join(tmp, "backlog.d", "FM-3.md"), "w",
                      encoding="utf-8") as f:
                f.write(_neu("FM-3", details="[gut](docs/ziel.md) [tot](../docs/ziel.md)"))
            cdl.REPO = tmp
            tot = [ref for _datei, ref, _ziel in cdl.find_dead_links()]
        self.assertEqual(tot, ["../docs/ziel.md"])


if __name__ == "__main__":
    unittest.main()
