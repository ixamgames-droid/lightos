"""PROC-19 — CI-Schnellweg fuer reine Doku-/Backlog-PRs.

Die CI faehrt fuer jeden PR die volle segmentierte Suite, auch wenn nur
Markdown geaendert wurde; das staut die Merge-Warteschlange. Aendert ein PR
AUSSCHLIESSLICH Doku, laufen in denselben Jobs (gleiche Namen — daran erkennt
``tools/pr_bereit.py`` die Checks) nur die Gates aus ``tools/doku_gates.txt``.

Vier Dinge werden hier festgehalten:

1. der Klassifizierer (``tools/geaenderte_dateien_klasse.py``) — Tabellentest
   mit Fallen; im Zweifel ``voll``;
2. der Git-Vergleich rechnet gegen den MERGE-BASE (ein Zweig "Code, danach
   Doku" ist ``voll``), und ``--ci`` ist ausserhalb eines Pull-Requests immer
   ``voll``;
3. die Gate-Liste: kein totes Muster, und jede Testdatei, die in ihrem Code
   eine Doku-Datei nennt, ist Gate oder bewusst ausgenommen;
4. die Struktur der ``ci.yml``: Job-Namen unveraendert, Schnellweg-Bedingung
   in jedem Job, Push nach ``main`` immer volle Suite, kein Pfadfilter.

Kein Qt, kein ``src``-Import.
"""
import ast
import fnmatch
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "tests"))

import geaenderte_dateien_klasse as gk  # noqa: E402
from test_ci_windows_legs import (  # noqa: E402
    _ci_text, _einrueckung, alle_with_werte, ci_jobs, job_schluessel, schritt_run)

SKRIPT = os.path.join(REPO, "tools", "geaenderte_dateien_klasse.py")

# ── 1. Klassifizierer ────────────────────────────────────────────────────────

DOKU_PFADE = (
    "README.md",
    "BACKLOG.md",
    "BACKLOG_ARCHIVE.md",
    "WORKFLOW.md",
    "COORDINATION.md",
    "CHANGELOG.md",
    "THIRD_PARTY_NOTICES.md",
    "changelog.d/2026-10-10-PROC-19.md",
    "changelog.d/README.md",
    "backlog.d/PROC-20.md",          # PROC-20: Backlog-Fragmente
    "backlog.d/README.md",
    "docs/ANLEITUNGEN.md",
    "docs/anleitung_efx/ANLEITUNG.md",
    "docs/anleitung_efx/ANLEITUNG.en.md",
    "docs/anleitung_efx/img/01_start.png",
    "docs/anleitung_efx/img/ablauf.gif",
    "docs/projektseite/img/kopf.JPG",
    "docs/a/b/c/d/bild.webp",
    "docs/skizze.svg",
    "docs/Datei mit Leerzeichen.md",
)

VOLL_PFADE = (
    # Code, Tests, Werkzeuge, CI
    "main.py",
    "src/core/engine.py",
    "tests/test_doc_links.py",
    "tools/pr_bereit.py",
    "tools/doku_gates.txt",
    "tools/geaenderte_dateien_klasse.py",
    ".github/workflows/ci.yml",
    "requirements.txt",
    "pytest.ini",
    ".gitignore",
    # Markdown AUSSERHALB der Doku-Orte
    "tools/README.md",                      # erzeugt, gegen den Code geprueft
    "tools/_archiv/README.md",
    "tests/README.md",
    "tests/fixtures/beispiel.md",
    "src/ui/hilfe.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    "fixtures/bibliothek/SCHEMA.md",
    "data/controller_library/README.md",
    "examples/README.md",
    "packaging/windows/LIESMICH.md",
    "changelog.d/unterordner/x.md",
    "backlog.d/unterordner/x.md",
    "backlog.d/PROC-20.txt",
    "backlog.dx/PROC-20.md",
    "tools/backlog.d/PROC-20.md",
    # Unter docs/, aber keine Doku
    "docs/capability_manifest.json",
    "docs/anleitung_efx/img/bilder.json",
    "docs/_walkthrough/render_editor.py",
    "docs/tutorial_matrix/_cap.ps1",
    "docs/Makefile",
    "docs/ohne_endung",
    "docs/show.lshow",
    "docs/x.md.py",
    # Assets ausserhalb von docs/
    "assets/icon.png",
    "src/ui/visualizer/assets/bild.png",
    "changelog.d/bild.png",
    "bild.png",
    "fixtures/geraet.json",
    # Fallen
    "docs/../src/core/engine.py",
    "docs/../README.md",
    "../README.md",
    "./README.md",
    "docs/./x.md",
    "/README.md",
    "/etc/docs/x.md",
    "docs//x.md",
    "docs/",
    "docs",
    "docs\\x.md",
    "docs\\..\\src\\x.py",
    "Docs/x.md",
    "DOCS/x.md",
    "docsx/x.md",
    "xdocs/README.md",
    "changelog.dx/x.md",
    " README.md",
    "README.md ",
    "README.md\n",
    "docs/x.md\tsrc/y.py",
    "",
    ".md/x.py",
    "README.md/engine.py",
)


class KlassifiziererTest(unittest.TestCase):

    def test_doku_pfade(self):
        for p in DOKU_PFADE:
            with self.subTest(pfad=p):
                self.assertTrue(gk.ist_doku(p))
                self.assertEqual(gk.klasse([p]), gk.DOKU)

    def test_alles_andere_ist_voll(self):
        for p in VOLL_PFADE:
            with self.subTest(pfad=p):
                self.assertFalse(gk.ist_doku(p))
                self.assertEqual(gk.klasse([p]), gk.VOLL)

    def test_nicht_text_ist_voll(self):
        for p in (None, 7, b"README.md", ["README.md"]):
            with self.subTest(pfad=p):
                self.assertFalse(gk.ist_doku(p))

    def test_eine_einzige_fremde_datei_kippt_alles(self):
        for stoerer in VOLL_PFADE:
            with self.subTest(stoerer=stoerer):
                self.assertEqual(gk.klasse(list(DOKU_PFADE) + [stoerer]), gk.VOLL)
        self.assertEqual(gk.klasse(DOKU_PFADE), gk.DOKU)

    def test_leere_liste_ist_voll(self):
        """Nichts geaendert heisst nicht 'nur Doku' — im Zweifel voll."""
        self.assertEqual(gk.klasse([]), gk.VOLL)
        self.assertEqual(gk.klasse(iter(())), gk.VOLL)

    def test_echte_dateien_des_repos(self):
        """Gegenprobe an der echten Ablage, nicht nur an erfundenen Pfaden."""
        self.assertTrue(gk.ist_doku("BACKLOG.md"))
        for p in ("tools/README.md", "docs/capability_manifest.json",
                  ".github/workflows/ci.yml"):
            self.assertTrue(os.path.exists(os.path.join(REPO, p)), p)
            self.assertFalse(gk.ist_doku(p), p)


# ── 2. Git-Vergleich ─────────────────────────────────────────────────────────

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class GitVergleichTest(unittest.TestCase):
    """Wegwerf-Repo im Temp-Ordner; das echte Repo wird nicht angefasst."""

    def setUp(self):
        # Windows: Git legt Objekte schreibgeschuetzt ab.
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.repo = self._tmp.name
        self.git("init", "-q", "-b", "main")
        self.schreibe("README.md", "start\n")
        self.schreibe("src/a.py", "x = 1\n")
        self.schreibe("docs/a.md", "a\n")
        self.commit("start")

    def git(self, *args):
        env = dict(os.environ, **_GIT_ENV)
        return subprocess.run(["git", "-C", self.repo, *args], check=True,
                              capture_output=True, text=True, env=env).stdout.strip()

    def schreibe(self, pfad, text):
        voll = os.path.join(self.repo, *pfad.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        with open(voll, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, text):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", text)
        return self.git("rev-parse", "HEAD")

    def zweig(self, name="pr"):
        self.git("checkout", "-q", "-b", name)

    def test_nur_doku(self):
        self.zweig()
        self.schreibe("docs/a.md", "neu\n")
        self.schreibe("BACKLOG.md", "| X |\n")
        self.commit("doku")
        k, grund = gk.klasse_gegen("main", self.repo)
        self.assertEqual(k, gk.DOKU, grund)

    def test_code_dann_doku_ist_voll(self):
        """DER Fall: der letzte Commit aendert nur Doku, davor steht Code."""
        self.zweig()
        self.schreibe("src/a.py", "x = 2\n")
        self.commit("code")
        self.schreibe("docs/a.md", "neu\n")
        self.commit("doku")
        self.assertEqual(
            self.git("diff", "--name-only", "HEAD~1", "HEAD"), "docs/a.md",
            "Testaufbau: der letzte Commit soll NUR Doku aendern")
        k, grund = gk.klasse_gegen("main", self.repo)
        self.assertEqual(k, gk.VOLL)
        self.assertIn("src/a.py", grund)

    def test_main_ist_weitergezogen(self):
        """Fremde Code-Commits auf main zaehlen nicht zum Zweig (Merge-Base)."""
        self.zweig()
        self.schreibe("docs/a.md", "neu\n")
        self.commit("doku")
        self.git("checkout", "-q", "main")
        self.schreibe("src/a.py", "x = 3\n")
        self.commit("code auf main")
        self.git("checkout", "-q", "pr")
        self.assertEqual(gk.klasse_gegen("main", self.repo)[0], gk.DOKU)

    def test_umbenennung_aus_dem_code_ist_voll(self):
        """``git mv src/a.py docs/a2.md``: der ALTE Pfad zaehlt mit."""
        self.zweig()
        self.git("mv", "src/a.py", "docs/a2.md")
        self.commit("verschoben")
        self.assertEqual(sorted(gk.geaenderte_dateien("main", self.repo)),
                         ["docs/a2.md", "src/a.py"])
        self.assertEqual(gk.klasse_gegen("main", self.repo)[0], gk.VOLL)

    def test_geloeschte_codedatei_ist_voll(self):
        self.zweig()
        self.git("rm", "-q", "src/a.py")
        self.commit("weg")
        self.assertEqual(gk.klasse_gegen("main", self.repo)[0], gk.VOLL)

    def test_keine_aenderung_ist_voll(self):
        self.zweig()
        self.assertEqual(gk.klasse_gegen("main", self.repo)[0], gk.VOLL)

    def test_git_fehler_ist_voll(self):
        self.assertIsNone(gk.geaenderte_dateien("gibt-es-nicht", self.repo))
        self.assertEqual(gk.klasse_gegen("gibt-es-nicht", self.repo)[0], gk.VOLL)
        kein_repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, kein_repo, True)
        self.assertEqual(gk.klasse_gegen("main", kein_repo)[0], gk.VOLL)

    # -- CI-Modus: der Checkout steht auf dem Test-Merge von GitHub ----------

    def _test_merge(self, mit_code):
        """Baut ``refs/pull/N/merge`` nach: main (Elter 1) + PR-Kopf (Elter 2)."""
        self.zweig()
        if mit_code:
            self.schreibe("src/a.py", "x = 2\n")
            self.commit("code")
        self.schreibe("docs/a.md", "neu\n")
        kopf = self.commit("doku")
        self.git("checkout", "-q", "main")
        self.schreibe("src/b.py", "y = 1\n")       # main zieht weiter
        self.commit("main weiter")
        self.git("checkout", "-q", "--detach")
        self.git("merge", "-q", "--no-ff", "-m", "Merge", "pr")
        return kopf

    def test_ci_doku_pr(self):
        kopf = self._test_merge(mit_code=False)
        k, grund = gk.ci_klasse(
            {"GITHUB_EVENT_NAME": "pull_request", "PR_KOPF_SHA": kopf}, self.repo)
        self.assertEqual(k, gk.DOKU, grund)

    def test_ci_code_pr_mit_doku_als_letztem_commit(self):
        kopf = self._test_merge(mit_code=True)
        k, _ = gk.ci_klasse(
            {"GITHUB_EVENT_NAME": "pull_request", "PR_KOPF_SHA": kopf}, self.repo)
        self.assertEqual(k, gk.VOLL)

    def test_ci_push_ist_immer_voll(self):
        """Auch wenn der Stand ein reiner Doku-Merge ist: Push -> volle Suite."""
        kopf = self._test_merge(mit_code=False)
        for ereignis in ("push", "workflow_dispatch", "schedule", "merge_group",
                         "pull_request_target", "", "PULL_REQUEST"):
            with self.subTest(ereignis=ereignis):
                k, _ = gk.ci_klasse(
                    {"GITHUB_EVENT_NAME": ereignis, "PR_KOPF_SHA": kopf}, self.repo)
                self.assertEqual(k, gk.VOLL)
        self.assertEqual(gk.ci_klasse({"PR_KOPF_SHA": kopf}, self.repo)[0], gk.VOLL)

    def test_ci_ohne_oder_mit_falschem_kopf_ist_voll(self):
        kopf = self._test_merge(mit_code=False)
        basis = self.git("rev-parse", "HEAD^1")
        for sha in ("", "   ", "0" * 40, basis, kopf[:12]):
            with self.subTest(sha=sha):
                k, _ = gk.ci_klasse(
                    {"GITHUB_EVENT_NAME": "pull_request", "PR_KOPF_SHA": sha}, self.repo)
                self.assertEqual(k, gk.VOLL)

    def test_ci_head_ist_kein_merge(self):
        """Checkout auf dem PR-Kopf statt auf dem Test-Merge: HEAD^1 waere nur
        der vorige Commit — genau die Luecke 'letzter Commit nur Doku'."""
        self.zweig()
        self.schreibe("src/a.py", "x = 2\n")
        self.commit("code")
        self.schreibe("docs/a.md", "neu\n")
        kopf = self.commit("doku")
        k, _ = gk.ci_klasse(
            {"GITHUB_EVENT_NAME": "pull_request", "PR_KOPF_SHA": kopf}, self.repo)
        self.assertEqual(k, gk.VOLL)

    def test_ci_flacher_klon_mit_tiefe_zwei_genuegt(self):
        """Die CI holt ``fetch-depth: 2`` — das muss fuer den Vergleich reichen."""
        kopf = self._test_merge(mit_code=False)
        self.git("branch", "-f", "merge")
        flach = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, flach, True)
        subprocess.run(["git", "clone", "-q", "--depth", "2", "--branch", "merge",
                        pathlib.Path(self.repo).as_uri(), flach], check=True,
                       capture_output=True, env=dict(os.environ, **_GIT_ENV))
        k, grund = gk.ci_klasse(
            {"GITHUB_EVENT_NAME": "pull_request", "PR_KOPF_SHA": kopf}, flach)
        self.assertEqual(k, gk.DOKU, grund)


class AufrufTest(unittest.TestCase):

    def _lauf(self, *args, **env):
        e = dict(os.environ, PYTHONUTF8="1")
        for k in ("GITHUB_EVENT_NAME", "PR_KOPF_SHA", "GITHUB_OUTPUT"):
            e.pop(k, None)
        e.update(env)
        return subprocess.run([sys.executable, SKRIPT, *args], capture_output=True,
                              text=True, encoding="utf-8", env=e, cwd=REPO, timeout=50)

    def test_ci_push_schreibt_voll_in_github_output(self):
        with tempfile.TemporaryDirectory() as d:
            aus = os.path.join(d, "out")
            r = self._lauf("--ci", GITHUB_EVENT_NAME="push", GITHUB_OUTPUT=aus)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "voll")
            with open(aus, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "klasse=voll\n")

    def test_ci_ohne_umgebung_ist_voll_und_scheitert_nicht(self):
        r = self._lauf("--ci")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "voll"), r.stderr)

    def test_stdout_ist_genau_ein_wort(self):
        r = self._lauf("--basis", "gibt-es-nicht")
        self.assertEqual((r.returncode, r.stdout), (0, "voll\n"), r.stderr)

    def test_gates_ausgabe(self):
        r = self._lauf("--gates")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), gk.doku_gates())


# ── 3. Gate-Liste ────────────────────────────────────────────────────────────

#: Was im kurzen Weg auf keinen Fall fehlen darf.
PFLICHT_GATES = (
    "tests/test_doc_links.py",
    "tests/test_doc_images.py",
    "tests/test_doc_removed_ui.py",
    "tests/test_doc13_anleitung_gruppen_matrizen.py",
    "tests/test_keine_privaten_dateien.py",
    "tests/test_keine_konfliktmarker.py",
    "tests/test_changelog_fragmente.py",
    "tests/test_backlog_lint.py",
    "tests/test_backlog_ids.py",
    "tests/test_backlog_compact.py",
    "tests/test_qa55_doku_und_backlog_gates.py",
    "tests/test_tools_index.py",
    "tests/test_proc19_doku_schnellweg.py",
)

_DOKU_NENNUNG = re.compile(
    r"\.md\b|(^|[\"'/\\ ])docs(/|\\|$)|changelog\.d|backlog\.d|BACKLOG")


def nennt_doku(quelle: str) -> list[str]:
    """Zeichenketten im CODE (ohne Docstrings), die eine Doku-Datei nennen."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)   # fremde Testdateien
        baum = ast.parse(quelle)
    docstrings = set()
    for k in ast.walk(baum):
        if isinstance(k, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = k.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
                    and isinstance(b[0].value.value, str):
                docstrings.add(id(b[0].value))
    return [k.value for k in ast.walk(baum)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
            and id(k) not in docstrings and _DOKU_NENNUNG.search(k.value)]


class GateListeTest(unittest.TestCase):

    def setUp(self):
        self.gates = gk.doku_gates()
        self.muster, self.ausgenommen = gk._muster()
        self.testdateien = sorted(n for n in os.listdir(os.path.join(REPO, "tests"))
                                  if n.startswith("test_") and n.endswith(".py"))

    def test_pflicht_gates_sind_dabei(self):
        for p in PFLICHT_GATES:
            with self.subTest(gate=p):
                self.assertIn(p, self.gates)

    def test_gates_existieren_und_sind_keine_handvoll(self):
        self.assertGreaterEqual(len(self.gates), 25)
        for p in self.gates:
            self.assertTrue(os.path.isfile(os.path.join(REPO, p)), p)

    def test_der_kurze_weg_ist_kurz(self):
        """Wer hier ``test_*.py`` eintraegt, hat den Schnellweg abgeschafft."""
        self.assertLess(len(self.gates), len(self.testdateien) / 5)

    def test_muster_fangen_keine_fremden_dateien(self):
        """``test_doc*`` haette ``test_dock_rotation_follow.py`` mitgenommen."""
        self.assertNotIn("tests/test_dock_rotation_follow.py", self.gates)

    def test_kein_totes_muster(self):
        """Ein Muster ohne Treffer ist ein umbenannter oder geloeschter Test —
        das Gate waere still verschwunden."""
        for m in self.muster + self.ausgenommen:
            with self.subTest(muster=m):
                self.assertTrue(fnmatch.filter(self.testdateien, m),
                                f"'{m}' in tools/doku_gates.txt trifft keine Testdatei")

    def test_nichts_ist_gate_und_ausnahme_zugleich(self):
        for n in self.testdateien:
            if any(fnmatch.fnmatchcase(n, m) for m in self.ausgenommen):
                self.assertNotIn("tests/" + n, self.gates)

    def test_jeder_test_der_doku_nennt_ist_gate_oder_ausnahme(self):
        """Das Netz unter dem Schnellweg: ein Test, der eine Anleitung, den
        Backlog oder ein Fragment liest, aber kein Gate ist, liefe fuer einen
        Doku-PR nie — erst der Push nach main wuerde rot."""
        offen = []
        for n in self.testdateien:
            if "tests/" + n in self.gates:
                continue
            if any(fnmatch.fnmatchcase(n, m) for m in self.ausgenommen):
                continue
            with open(os.path.join(REPO, "tests", n), encoding="utf-8") as fh:
                treffer = nennt_doku(fh.read())
            if treffer:
                offen.append(f"{n}: {treffer[0][:50]!r}")
        self.assertEqual(
            offen, [],
            "Diese Testdateien nennen Doku-Dateien, stehen aber nicht in "
            "tools/doku_gates.txt. Liest der Test die Doku wirklich: als Gate "
            "eintragen. Sonst mit '!' und Grund ausnehmen.")

    def test_erkennung_der_nennung(self):
        self.assertTrue(nennt_doku('p = os.path.join(R, "docs", "a")'))
        self.assertTrue(nennt_doku('p = "BACKLOG.md"'))
        self.assertTrue(nennt_doku('p = R / "changelog.d"'))
        self.assertTrue(nennt_doku('p = R / "backlog.d"'))
        self.assertFalse(nennt_doku('"""steht in docs/a.md"""\nx = "dock"'))
        self.assertFalse(nennt_doku('def f():\n    """siehe README.md"""\n    return 1'))


# ── 4. Struktur der ci.yml ───────────────────────────────────────────────────

#: Daran erkennen ``tools/pr_bereit.py`` und ``tools/_ci_beobachtend.py`` die
#: Checks. Der Schnellweg darf KEINEN davon aendern oder weglassen.
JOB_NAMEN = {
    "linux": "Linux — volle Suite (segmentiert)",
    "test": "Windows-Smoke (Python ${{ matrix.python-version }})",
    "windows-arm": "Windows-ARM64 — volle Suite (segmentiert, beobachtend)",
}
KLASSE_SCHRITT = "Aenderungsklasse bestimmen (PROC-19)"
NUR_VOLL = "steps.klasse.outputs.klasse != 'doku'"
NUR_DOKU = "steps.klasse.outputs.klasse == 'doku'"

#: Schritte, die im Doku-Fall NICHT laufen duerfen (die teure Arbeit).
TEUER = {
    "linux": ("Volle Suite (segmentiert)",),
    "test": ("Kern-Abhaengigkeiten installieren", "Unit-Tests ausfuehren"),
    "windows-arm": ("venv + Abhaengigkeiten (ohne native Optionale)",
                    "Volle Suite (segmentiert)"),
}


def schritte(job_zeilen):
    """``[(Name, {Schluessel: Wert}, Zeilen)]`` der Schritte eines Jobs."""
    ergebnis, aktuell = [], None
    for z in job_zeilen:
        g = z.strip()
        if _einrueckung(z) == 6 and g.startswith("- "):
            aktuell = ["", {}, []]
            ergebnis.append(aktuell)
            g = g[2:]
            tiefe_ok = True
        else:
            tiefe_ok = _einrueckung(z) == 8
        if aktuell is None or not g or g.startswith("#"):
            continue
        aktuell[2].append(z)
        if tiefe_ok and re.match(r"[A-Za-z_-]+:", g):
            k, _, v = g.partition(":")
            v = v.split(" #", 1)[0].strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]             # nur ein UMSCHLIESSENDES Paar
            aktuell[1][k] = v
            if k == "name":
                aktuell[0] = aktuell[1][k]
    return [tuple(s) for s in ergebnis]


def schritt_env(zeilen):
    """Der ``env:``-Block eines Schritts als normalisierter Text."""
    block, drin = [], False
    for z in zeilen:
        if z.lstrip().startswith("#"):
            continue
        if _einrueckung(z) == 8:
            drin = z.strip() == "env:"
            continue
        if drin:
            block.append(z.strip())
    return " ".join(block)


class CiStrukturTest(unittest.TestCase):

    def setUp(self):
        self.text = _ci_text()
        self.jobs = ci_jobs(self.text)

    def test_job_namen_unveraendert(self):
        self.assertEqual(set(self.jobs), set(JOB_NAMEN))
        for key, name in JOB_NAMEN.items():
            with self.subTest(job=key):
                self.assertEqual(job_schluessel(self.jobs[key], "name"), name)

    def test_kein_job_wird_als_ganzes_uebersprungen(self):
        """Ein uebersprungener JOB erzeugt keinen bzw. einen 'skipped'-Check —
        der kurze Weg laeuft deshalb INNERHALB der Jobs, ueber Schritte."""
        for key, zeilen in self.jobs.items():
            with self.subTest(job=key):
                self.assertIsNone(job_schluessel(zeilen, "if"))

    def test_kein_pfadfilter_am_workflow(self):
        """``paths``/``paths-ignore`` liesse den ganzen Workflow ausfallen: der
        PR haette dann GAR KEINE Checks, und pr_bereit meldet 'nie geprueft'."""
        kopf = self.text.split("\njobs:", 1)[0]
        self.assertNotRegex(kopf, r"(?m)^\s*paths(-ignore)?\s*:")

    def test_push_nach_main_loest_weiter_aus(self):
        kopf = self.text.split("\njobs:", 1)[0]
        self.assertRegex(kopf, r'push:\s*\n\s*branches:\s*\[[^\]]*"main"')
        self.assertRegex(kopf, r'pull_request:\s*\n\s*branches:\s*\[[^\]]*"main"')

    def test_klasse_schritt_in_jedem_job(self):
        for key, zeilen in self.jobs.items():
            with self.subTest(job=key):
                treffer = [s for s in schritte(zeilen) if s[0] == KLASSE_SCHRITT]
                self.assertEqual(len(treffer), 1)
                _, werte, _z = treffer[0]
                self.assertEqual(werte.get("id"), "klasse")
                # Push nach main: der Schritt laeuft gar nicht, die Ausgabe
                # bleibt leer, und leer heisst volle Suite.
                self.assertEqual(werte.get("if"), "github.event_name == 'pull_request'")
                self.assertEqual(schritt_run(zeilen, KLASSE_SCHRITT),
                                 "python tools/geaenderte_dateien_klasse.py --ci")
                self.assertIn("PR_KOPF_SHA: ${{ github.event.pull_request.head.sha }}",
                              schritt_env(_z))

    def test_klasse_schritt_steht_nach_checkout_und_python(self):
        for key, zeilen in self.jobs.items():
            with self.subTest(job=key):
                namen = [s[0] for s in schritte(zeilen)]
                uses = [s[1].get("uses", "") for s in schritte(zeilen)]
                i = namen.index(KLASSE_SCHRITT)
                self.assertTrue(any("actions/checkout" in u for u in uses[:i]))
                self.assertTrue(any("actions/setup-python" in u for u in uses[:i]))

    def test_checkout_holt_den_test_merge_mit_eltern(self):
        """Ohne ``fetch-depth: 2`` fehlen die Eltern des Test-Merge (-> immer
        voll); mit ``ref:`` stuende HEAD nicht mehr auf dem Test-Merge."""
        for key, zeilen in self.jobs.items():
            with self.subTest(job=key):
                werte = alle_with_werte(zeilen, "actions/checkout")
                self.assertEqual(len(werte), 1)
                self.assertEqual(werte[0].get("fetch-depth"), "2")
                self.assertNotIn("ref", werte[0])

    def test_bedingungen_fallen_auf_voll(self):
        """Jede Bedingung haengt an ``'doku'``. Ein ``== 'voll'`` wuerde bei
        leerer Ausgabe (Push, Fehler im Klassenschritt) die Suite UEBERSPRINGEN."""
        self.assertNotIn("== 'voll'", self.text)
        self.assertNotIn("!= 'voll'", self.text)
        for key, zeilen in self.jobs.items():
            for name, werte, _z in schritte(zeilen):
                bed = werte.get("if", "")
                if "steps.klasse" in bed:
                    with self.subTest(job=key, schritt=name):
                        self.assertIn(bed, (NUR_VOLL, NUR_DOKU))

    def test_teure_schritte_nur_im_vollen_fall(self):
        for key, namen in TEUER.items():
            vorhanden = {s[0]: s[1] for s in schritte(self.jobs[key])}
            for name in namen:
                with self.subTest(job=key, schritt=name):
                    self.assertIn(name, vorhanden)
                    self.assertEqual(vorhanden[name].get("if"), NUR_VOLL)

    def test_jeder_job_hat_genau_einen_doku_schritt(self):
        for key, zeilen in self.jobs.items():
            with self.subTest(job=key):
                doku = [s for s in schritte(zeilen) if s[1].get("if") == NUR_DOKU]
                self.assertEqual(len(doku), 1)
                self.assertTrue(doku[0][0].startswith("Doku-PR:"), doku[0][0])

    def test_linux_faehrt_im_doku_fall_die_gates(self):
        zeilen = self.jobs["linux"]
        doku = [s for s in schritte(zeilen) if s[1].get("if") == NUR_DOKU][0]
        run = schritt_run(zeilen, doku[0])
        self.assertIn("./tools/verify_loop.sh --doku", run)
        voll = [s for s in schritte(zeilen) if s[0] == "Volle Suite (segmentiert)"][0]
        self.assertNotIn("--doku", schritt_run(zeilen, voll[0]))
        self.assertTrue(schritt_env(voll[2]))
        self.assertEqual(schritt_env(doku[2]), schritt_env(voll[2]),
                         "Doku-Schritt und volle Suite muessen dieselbe Umgebung "
                         "haben (WebGL-Flags, Exit-Haertung)")

    def test_segment_logs_werden_in_beiden_faellen_hochgeladen(self):
        for key in ("linux", "windows-arm"):
            with self.subTest(job=key):
                s = [x for x in schritte(self.jobs[key])
                     if x[0] == "Segment-Logs bei Fehlschlag hochladen"]
                self.assertEqual(len(s), 1)
                self.assertEqual(s[0][1].get("if"), "failure()")


class LokalerSchalterTest(unittest.TestCase):

    def setUp(self):
        with open(os.path.join(REPO, "tools", "verify_loop.sh"), encoding="utf-8") as fh:
            self.sh = fh.read()

    def test_verify_loop_kennt_doku(self):
        self.assertIn('"--doku"', self.sh)
        self.assertIn("geaenderte_dateien_klasse.py --gates", self.sh)

    def test_doku_lauf_nimmt_die_voll_suiten_sperre(self):
        """Der Schalter wird VOR ``_verify_lock "$@"`` abgeraeumt — der Lauf
        leert ``.pytest_segments`` und darf nicht neben einem vollen Gate laufen."""
        i_shift = self.sh.index('if [ "${1:-}" = "--doku" ]; then')
        i_lock = self.sh.index('\n_verify_lock "$@"\n')
        self.assertLess(i_shift, i_lock)
        self.assertIn("shift", self.sh[i_shift:i_lock])

    @unittest.skipUnless(shutil.which("bash") and os.name != "nt", "braucht bash")
    def test_doku_mit_weiteren_argumenten_ist_ein_fehler(self):
        r = subprocess.run(
            ["bash", os.path.join(REPO, "tools", "verify_loop.sh"), "--doku", "tests/x.py"],
            capture_output=True, text=True, cwd=REPO, timeout=50,
            env=dict(os.environ, LIGHTOS_VERIFY_DRYRUN="1", LIGHTOS_VERIFY_NOLOCK="1"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--doku", r.stdout)


class DokuTest(unittest.TestCase):
    """Der Schnellweg steht dort, wo man ihn sucht."""

    def _lies(self, name):
        with open(os.path.join(REPO, name), encoding="utf-8") as fh:
            return fh.read()

    def test_workflow_md_nennt_schnellweg_und_werkzeug(self):
        t = self._lies("WORKFLOW.md")
        self.assertIn("PROC-19", t)
        self.assertIn("tools/geaenderte_dateien_klasse.py", t)
        self.assertIn("tools/doku_gates.txt", t)
        self.assertIn("verify_loop.sh --doku", t)

    def test_coordination_md_nennt_schnellweg(self):
        t = self._lies("COORDINATION.md")
        self.assertIn("PROC-19", t)
        self.assertIn("tools/doku_gates.txt", t)


if __name__ == "__main__":
    unittest.main()
