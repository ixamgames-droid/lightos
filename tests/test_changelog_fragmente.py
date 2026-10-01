"""PROC-09: CHANGELOG-Fragmente unter ``changelog.d/`` statt Kopf-Konflikten.

Der CHANGELOG-Kopf war zwischen zwei parallelen Sitzungen ein garantierter
Konflikt (81 % Konfliktquote der Zweig-Merges in der Parallelphase). Jetzt
bringt jeder PR eine eigene Fragment-Datei mit; ``tools/changelog_sammeln.py``
sortiert sie beim Release unter ``## [Unreleased]`` ein.

Geprueft wird dreierlei:

1. **Sammeln** — Reihenfolge neueste zuerst, Formfehler blockieren, der
   Trockenlauf aendert nichts, Zeilenenden bleiben, wie sie waren.
2. **Waechter** — eine Hand-Aenderung an CHANGELOG.md seit der Abzweigung von
   origin/main faellt auf; ein Sammel-Lauf, ein ``changelog:``-Commit und ein
   Zweig hinter main dagegen NICHT; ohne origin/main (CI) still bestanden.
3. **Der echte Baum** — Fragmente sind wohlgeformt, und der Waechter ist auf
   dem aktuellen Zweig gruen.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
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


cs = _modul("changelog_sammeln")

KOPF = ("# Changelog\n\nText.\n\n---\n\n## [Unreleased]\n\n"
        "### 2026-09-30 — Alt (X-1)\n\n#### Behoben\n\n- alt\n")


def _fragment(titel: str, datum: str = "2026-10-01") -> str:
    return f"### {datum} — {titel}\n\n#### Behoben\n\n- {titel} behoben\n"


def _still(*_a, **_k):
    pass


class FragmentFormTest(unittest.TestCase):

    def test_gueltiges_fragment(self):
        self.assertEqual(cs.pruefe_fragment("2026-10-01-UI-64.md",
                                            _fragment("A (UI-64)")), [])

    def test_formfehler_werden_gemeldet(self):
        faelle = {
            ("2026-10-1-UI-64.md", _fragment("A")): "Dateiname",
            ("2026-10-01-UI-64.md", "   \n"): "leer",
            ("2026-10-01-UI-64.md", "- nur eine Zeile\n"): "'### '",
            ("2026-10-01-UI-64.md", "### T\n\n## [Unreleased]\n"): "zerbrechen",
        }
        for (name, text), erwartet in faelle.items():
            with self.subTest(name=name, text=text):
                fehler = cs.pruefe_fragment(name, text)
                self.assertTrue(any(erwartet in f for f in fehler), fehler)

    def test_ueberschrift_im_codeblock_ist_erlaubt(self):
        text = "### T\n\n```\n## kein Abschnitt\n```\n"
        self.assertEqual(cs.pruefe_fragment("2026-10-01-A-1.md", text), [])

    def test_readme_ist_kein_fragment(self):
        self.assertFalse(cs.ist_fragment_name("README.md"))
        self.assertTrue(cs.ist_fragment_name("2026-10-01-UI-64_UI-65.md"))


class BaueChangelogTest(unittest.TestCase):

    def test_unter_unreleased_vor_dem_bisher_obersten_eintrag(self):
        neu = cs.baue_changelog(KOPF, [_fragment("B"), _fragment("A")])
        i_unrel = neu.index("## [Unreleased]")
        i_b, i_a = neu.index("— B"), neu.index("— A")
        i_alt = neu.index("— Alt")
        self.assertTrue(i_unrel < i_b < i_a < i_alt, neu)
        self.assertTrue(neu.startswith("# Changelog\n\nText."))
        self.assertIn("## [Unreleased]\n\n### 2026-10-01 — B", neu)
        self.assertIn("- A behoben\n\n### 2026-09-30 — Alt", neu)

    def test_ohne_unreleased_kein_stilles_anhaengen(self):
        with self.assertRaises(ValueError):
            cs.baue_changelog("# Changelog\n\n### alt\n", [_fragment("A")])


class SammelnTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        (self.repo / "changelog.d").mkdir()
        (self.repo / "CHANGELOG.md").write_bytes(KOPF.encode("utf-8"))

    def _frag(self, name: str, text: str):
        (self.repo / "changelog.d" / name).write_text(text, encoding="utf-8")

    def test_neueste_zuerst_und_fragmente_weg(self):
        self._frag("2026-09-30-B-1.md", _fragment("Mitte", "2026-09-30"))
        self._frag("2026-10-02-C-1.md", _fragment("Neu", "2026-10-02"))
        (self.repo / "changelog.d" / "README.md").write_text("# x\n", encoding="utf-8")
        self.assertEqual(cs.sammeln(self.repo, ausgabe=_still), 0)
        text = (self.repo / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertLess(text.index("— Neu"), text.index("— Mitte"))
        self.assertLess(text.index("— Mitte"), text.index("— Alt"))
        self.assertEqual(sorted(p.name for p in (self.repo / "changelog.d").iterdir()),
                         ["README.md"], "Fragmente muessen nach dem Sammeln weg sein")

    def test_trockenlauf_aendert_nichts(self):
        self._frag("2026-10-01-A-1.md", _fragment("A"))
        vorher = (self.repo / "CHANGELOG.md").read_bytes()
        self.assertEqual(cs.sammeln(self.repo, pruefen=True, ausgabe=_still), 0)
        self.assertEqual((self.repo / "CHANGELOG.md").read_bytes(), vorher)
        self.assertTrue((self.repo / "changelog.d" / "2026-10-01-A-1.md").exists())

    def test_formfehler_blockiert_alles(self):
        self._frag("2026-10-01-A-1.md", _fragment("A"))
        self._frag("2026-10-01-B-1.md", "ohne Ueberschrift\n")
        vorher = (self.repo / "CHANGELOG.md").read_bytes()
        self.assertEqual(cs.sammeln(self.repo, ausgabe=_still), 1)
        self.assertEqual((self.repo / "CHANGELOG.md").read_bytes(), vorher)
        self.assertTrue((self.repo / "changelog.d" / "2026-10-01-A-1.md").exists())

    def test_falsch_benannte_datei_wird_nicht_still_vergessen(self):
        self._frag("2026-1-01-A-1.md", _fragment("A"))
        self.assertEqual(cs.sammeln(self.repo, ausgabe=_still), 1)

    def test_crlf_bleibt_crlf(self):
        """Windows-Checkout (eol=lf im Repo, CRLF im Arbeitsbaum)."""
        (self.repo / "CHANGELOG.md").write_bytes(KOPF.replace("\n", "\r\n").encode("utf-8"))
        (self.repo / "changelog.d" / "2026-10-01-A-1.md").write_bytes(
            _fragment("A").replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(cs.sammeln(self.repo, ausgabe=_still), 0)
        roh = (self.repo / "CHANGELOG.md").read_bytes()
        self.assertNotIn(b"\r\r", roh)
        self.assertEqual(roh.count(b"\n"), roh.count(b"\r\n"), "gemischte Zeilenenden")
        self.assertIn("— A".encode("utf-8"), roh)

    def test_ohne_fragmente_nichts_zu_tun(self):
        vorher = (self.repo / "CHANGELOG.md").read_bytes()
        self.assertEqual(cs.sammeln(self.repo, ausgabe=_still), 0)
        self.assertEqual((self.repo / "CHANGELOG.md").read_bytes(), vorher)


class DiffZeilenTest(unittest.TestCase):

    def test_nur_datei_koepfe_werden_uebersprungen(self):
        diff = ("diff --git a/CHANGELOG.md b/CHANGELOG.md\n"
                "index 1111111..2222222 100644\n"
                "--- a/CHANGELOG.md\n+++ b/CHANGELOG.md\n"
                "@@ -5 +4,0 @@\n----\n"
                "@@ -9,0 +9,2 @@\n+---\n+++ x\n"
                "diff --git a/neu.md b/neu.md\n"
                "--- /dev/null\n+++ b/neu.md\n@@ -0,0 +1 @@\n+-- y\n")
        plus, minus = cs._diff_zeilen(diff)
        self.assertEqual(minus, ["---"])
        self.assertEqual(plus, ["---", "++ x", "-- y"])


class _GitRepo(unittest.TestCase):
    """Wegwerf-Repo mit einem kuenstlichen ``origin/main``."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        self.env = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="t@example.invalid",
                        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="t@example.invalid")
        self.git("init", "-q", "-b", "main")
        self.git("config", "core.autocrlf", "false")
        (self.repo / "changelog.d").mkdir()
        (self.repo / "CHANGELOG.md").write_text(KOPF, encoding="utf-8")
        self.commit("start")

    def git(self, *args, datum: str | None = None) -> str:
        env = dict(self.env)
        if datum:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = datum
        p = subprocess.run(("git", *args), cwd=self.repo, capture_output=True,
                           env=env)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        return p.stdout.decode("utf-8").strip()

    def commit(self, betreff: str, datum: str | None = None):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", betreff, datum=datum)

    def main_hier_festhalten(self):
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def frag(self, name: str, text: str):
        (self.repo / "changelog.d" / name).write_text(text, encoding="utf-8")

    def hand_eintrag(self):
        p = self.repo / "CHANGELOG.md"
        p.write_text(p.read_text(encoding="utf-8").replace(
            "## [Unreleased]\n\n", "## [Unreleased]\n\n### 2026-10-01 — Hand\n\n- x\n\n"),
            encoding="utf-8")


class WaechterTest(_GitRepo):

    def test_ohne_origin_main_still_bestanden(self):
        """So sieht der CI-Lauf aus: flacher PR-Merge-Commit, kein origin/main."""
        self.hand_eintrag()
        self.assertEqual(cs.direkte_aenderungen(self.repo), [])

    def test_ausserhalb_von_git_still_bestanden(self):
        with tempfile.TemporaryDirectory() as leer:
            self.assertEqual(cs.direkte_aenderungen(Path(leer)), [])

    def test_unveraendert_ist_gruen(self):
        self.main_hier_festhalten()
        self.frag("2026-10-01-A-1.md", _fragment("A"))   # neues Fragment: genau richtig
        self.commit("feat: A")
        self.assertEqual(cs.direkte_aenderungen(self.repo), [])

    def test_hand_eintrag_faellt_auf_committet_und_uncommittet(self):
        self.main_hier_festhalten()
        self.hand_eintrag()
        befunde = cs.direkte_aenderungen(self.repo)
        self.assertTrue(befunde and "direkt eingefuegt" in befunde[0], befunde)
        self.commit("feat: mit Hand-Eintrag")
        self.assertTrue(cs.direkte_aenderungen(self.repo))

    def test_entfernte_zeile_faellt_auf(self):
        self.main_hier_festhalten()
        p = self.repo / "CHANGELOG.md"
        p.write_text(p.read_text(encoding="utf-8").replace("- alt\n", ""), encoding="utf-8")
        befunde = cs.direkte_aenderungen(self.repo)
        self.assertTrue(any("entfernt" in b for b in befunde), befunde)

    def test_sammel_lauf_ist_erlaubt(self):
        self.frag("2026-10-01-A-1.md", _fragment("A"))
        self.frag("2026-10-02-B-1.md", _fragment("B", "2026-10-02"))
        self.commit("feat: zwei Fragmente")
        self.main_hier_festhalten()
        self.assertEqual(cs.sammeln(self.repo, ausgabe=_still), 0)
        # Vor UND nach dem Commit — Betreff bewusst OHNE Marker.
        self.assertEqual(cs.direkte_aenderungen(self.repo), [])
        self.commit("release: alles einsammeln")
        self.assertEqual(cs.direkte_aenderungen(self.repo), [])

    def test_sammel_lauf_plus_hand_zeile_faellt_auf(self):
        self.frag("2026-10-01-A-1.md", _fragment("A"))
        self.commit("feat: Fragment")
        self.main_hier_festhalten()
        cs.sammeln(self.repo, ausgabe=_still)
        self.hand_eintrag()
        self.assertTrue(cs.direkte_aenderungen(self.repo))

    def test_marker_commit_erlaubt_bewusste_korrektur(self):
        self.main_hier_festhalten()
        self.hand_eintrag()
        self.commit("changelog: ID UI-99 in UI-98 umbenannt")
        self.assertEqual(cs.direkte_aenderungen(self.repo), [])

    def test_entfernte_trennlinie_faellt_auf(self):
        """``---`` im Inhalt wird im Diff zu ``----`` — kein Datei-Kopf."""
        self.main_hier_festhalten()
        p = self.repo / "CHANGELOG.md"
        p.write_text(p.read_text(encoding="utf-8").replace("---\n\n", "", 1),
                     encoding="utf-8")
        befunde = cs.direkte_aenderungen(self.repo)
        self.assertTrue(any("entfernt" in b for b in befunde), befunde)

    def _release_schritt(self):
        p = self.repo / "CHANGELOG.md"
        p.write_text(p.read_text(encoding="utf-8").replace(
            "## [Unreleased]\n\n",
            "## [Unreleased]\n\n## [1.2.0] — 2026-10-01\n\n"), encoding="utf-8")

    def test_release_schritt_ohne_marker_faellt_auf(self):
        self.main_hier_festhalten()
        self._release_schritt()
        self.commit("release: 1.2.0")
        self.assertTrue(cs.direkte_aenderungen(self.repo))

    def test_release_schritt_mit_marker_erlaubt(self):
        """Der in AGENTS.md/WORKFLOW.md genannte Betreff ``changelog: release …``."""
        self.main_hier_festhalten()
        self._release_schritt()
        self.commit("changelog: release 1.2.0")
        self.assertEqual(cs.direkte_aenderungen(self.repo), [])

    def test_zweig_hinter_main_bekommt_main_nicht_angelastet(self):
        """Kein Fehlalarm, wenn auf main inzwischen gesammelt wurde."""
        start = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "-b", "feat/x")
        self.frag("2026-10-01-X-1.md", _fragment("X"))
        self.commit("feat: X")
        self.git("checkout", "-q", "main")
        self.hand_eintrag()
        self.commit("changelog: sammeln")
        self.main_hier_festhalten()
        self.git("checkout", "-q", "feat/x")
        self.assertNotEqual(self.git("rev-parse", "origin/main"), start)
        self.assertEqual(cs.direkte_aenderungen(self.repo), [])
        # ... auch nachdem der Zweig main hereingeholt hat (Merge-Commit).
        self.git("merge", "-q", "--no-edit", "origin/main")
        self.assertEqual(cs.direkte_aenderungen(self.repo), [])

    def test_gleicher_tag_nach_merge_reihenfolge(self):
        """Gleiches Datum im Namen: zuletzt gelandet = oben (wie bisher von Hand)."""
        self.frag("2026-10-01-ZZZ-1.md", _fragment("Zuerst"))
        self.commit("feat: zuerst", datum="2026-10-01T08:00:00")
        self.frag("2026-10-01-AAA-1.md", _fragment("Danach"))
        self.commit("feat: danach", datum="2026-10-01T12:00:00")
        namen = [p.name for p in cs.fragmente(self.repo)]
        self.assertEqual(namen, ["2026-10-01-AAA-1.md", "2026-10-01-ZZZ-1.md"])


class EchterBaumTest(unittest.TestCase):

    def test_fragmente_sind_wohlgeformt(self):
        self.assertEqual(cs.fremde_dateien(REPO), [],
                         "Datei in changelog.d/ ohne gueltigen Fragmentnamen — "
                         "sie wuerde nie gesammelt")
        fehler = []
        for p in cs.fragmente(REPO):
            fehler += cs.pruefe_fragment(p.name, p.read_text(encoding="utf-8"))
        self.assertEqual(fehler, [])

    def test_keine_direkte_changelog_aenderung_auf_diesem_zweig(self):
        befunde = cs.direkte_aenderungen(REPO)
        self.assertEqual(
            befunde, [],
            "CHANGELOG.md wurde seit origin/main direkt bearbeitet. Den Eintrag "
            "bitte als Fragment unter changelog.d/<datum>-<ID>.md anlegen "
            "(siehe changelog.d/README.md); bewusste Korrekturen alter "
            "Eintraege mit Commit-Betreff 'changelog: …'. Befunde: "
            + "; ".join(befunde))

    def test_regel_steht_in_agents_md(self):
        text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("changelog.d/", text)
        self.assertIn("changelog_sammeln.py", text)

    def test_release_betreff_steht_in_agents_und_workflow(self):
        """Der Release-Schritt braucht den Marker-Betreff — sonst Waechter-Alarm."""
        for name in ("AGENTS.md", "WORKFLOW.md"):
            text = (REPO / name).read_text(encoding="utf-8")
            self.assertIn("changelog: release", text, name)


class FragmentLinksTest(unittest.TestCase):
    """Fragment-Links gelten ab dem Repo-Wurzelverzeichnis (wie in CHANGELOG.md)."""

    def test_links_werden_von_der_wurzel_aus_aufgeloest(self):
        cdl = _modul("check_doc_links")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "docs"))
            os.makedirs(os.path.join(tmp, "changelog.d"))
            with open(os.path.join(tmp, "docs", "ziel.md"), "w", encoding="utf-8") as f:
                f.write("# Ziel\n")
            with open(os.path.join(tmp, "CHANGELOG.md"), "w", encoding="utf-8") as f:
                f.write("# Changelog\n")
            with open(os.path.join(tmp, "changelog.d", "2026-10-01-A-1.md"), "w",
                      encoding="utf-8") as f:
                f.write("### T\n\n- [gut](docs/ziel.md) [tot](../docs/ziel.md)\n")
            cdl.REPO = tmp
            tot = [ref for _datei, ref, _ziel in cdl.find_dead_links()]
        self.assertEqual(tot, ["../docs/ziel.md"])


if __name__ == "__main__":
    unittest.main()
