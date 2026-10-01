"""Waechter: was die Windows-Legs der CI wirklich fahren (XPLAT-40).

Warum es diesen Waechter gibt
-----------------------------
Der Windows-Smoke (Job ``test``) faehrt eine HANDVERLESENE Liste von
Testzielen, nicht die volle Suite. Was nicht auf der Liste steht, prueft auf
Windows nur das lokale Gate eines Rechners — und genau so blieb die Sandbox-
Undichtigkeit des Bild-Werkzeugs (USERPROFILE/LOCALAPPDATA, XPLAT-39) bis zur
Rig-Abnahme unentdeckt: die Linux-CI war gruen, weil Linux ``HOME`` liest.

XPLAT-40 nimmt die Sandbox-Tests aus ``tests/test_anleitungsbilder.py`` in den
Smoke. Dieser Waechter haelt fest, dass sie dort BLEIBEN, und dass jedes Ziel
der Liste existiert — ein Tippfehler in einem Pfad liesse pytest sonst mit
"file or directory not found" abbrechen, ein falscher Klassenname mit
"no tests ran" (beides faellt erst auf GitHub auf).

Zum Parser
----------
Wie ``test_ci_artefakte_nicht_versteckt.py``: PyYAML ist im venv nicht
installiert, ein Waechter mit eigener Abhaengigkeit wird nicht gefahren. Der
Parser liest nur die Form, um die es geht — Jobs an der Einrueckung, den Schritt
am ``name:`` und dessen ``run:``-Block.
"""
import os
import re
import shlex
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CI = os.path.join(REPO, ".github", "workflows", "ci.yml")

SMOKE_JOB = "test"
SMOKE_SCHRITT = "Unit-Tests ausfuehren"

#: Was XPLAT-40 im Windows-Smoke verlangt. ``WindowsHomeTest`` ist der Test zu
#: XPLAT-39 (USERPROFILE/LOCALAPPDATA in der Sandbox), ``SandboxRiegelTest`` der
#: Riegel gegen eine Sandbox nach dem ersten ``src``-Import.
PFLICHT_IM_SMOKE = (
    "tests/test_anleitungsbilder.py::WindowsHomeTest",
    "tests/test_anleitungsbilder.py::SandboxRiegelTest",
)


def _einrueckung(zeile: str) -> int:
    return len(zeile) - len(zeile.lstrip(" "))


def ci_jobs(text: str) -> dict[str, list[str]]:
    """``{Job-Name: Zeilen des Blocks}`` fuer alles unter ``jobs:``."""
    zeilen = text.splitlines()
    try:
        start = next(i for i, z in enumerate(zeilen) if z.rstrip() == "jobs:") + 1
    except StopIteration:
        return {}
    jobs: dict[str, list[str]] = {}
    aktuell = None
    for z in zeilen[start:]:
        if z.strip() and not z.startswith(" "):
            break                       # naechster Top-Level-Schluessel
        g = z.strip()
        if _einrueckung(z) == 2 and g.endswith(":") and not g.startswith("#") \
                and ": " not in g:
            aktuell = g[:-1]
            jobs[aktuell] = []
            continue
        if aktuell is not None:
            jobs[aktuell].append(z)
    return jobs


def schritt_run(job_zeilen: list[str], name: str) -> str | None:
    """Der ``run:``-Text des Schritts ``name`` (Block- oder Einzeiler-Form)."""
    for i, z in enumerate(job_zeilen):
        g = z.strip()
        if not g.startswith("- name:"):
            continue
        if g[len("- name:"):].strip().strip("'\"") != name:
            continue
        tiefe = _einrueckung(z) + 2     # Schluessel des Schritts
        for j in range(i + 1, len(job_zeilen)):
            zj = job_zeilen[j]
            if not zj.strip() or zj.lstrip().startswith("#"):
                continue
            if _einrueckung(zj) < tiefe:
                break                   # naechster Schritt bzw. Job-Ende
            if _einrueckung(zj) == tiefe and zj.strip().startswith("run:"):
                rest = zj.strip()[len("run:"):].strip()
                if rest and rest not in ("|", ">", "|-", ">-"):
                    return rest
                block = []
                for zk in job_zeilen[j + 1:]:
                    if zk.strip() and _einrueckung(zk) <= tiefe:
                        break
                    block.append(zk.strip())
                return "\n".join(block)
        return None
    return None


def pytest_ziele(run: str) -> list[str]:
    """Positionsargumente der ``pytest``-Aufrufe (Pfade/Node-IDs, keine Optionen)."""
    ziele = []
    for zeile in run.replace("\\\n", " ").splitlines():
        if "pytest" not in zeile or zeile.lstrip().startswith("#"):
            continue
        teile = shlex.split(zeile, posix=True)
        try:
            ab = next(i for i, t in enumerate(teile) if t == "pytest") + 1
        except StopIteration:
            continue
        ueberspringe = False
        for t in teile[ab:]:
            if ueberspringe:
                ueberspringe = False
                continue
            if t in ("-k", "-m", "-p", "-c", "--tb", "--timeout", "-o"):
                ueberspringe = True
                continue
            if t.startswith("-"):
                continue
            ziele.append(t)
    return ziele


def deckt_ab(ziele: list[str], pflicht: str) -> bool:
    """Laeuft ``pflicht`` mit, weil es selbst oder seine Datei gelistet ist?"""
    datei = pflicht.split("::", 1)[0]
    return any(z == pflicht or z == datei or pflicht.startswith(z + "::")
               for z in ziele)


def kaputte_ziele(ziele: list[str], repo: str = REPO) -> list[str]:
    """Ziele, deren Datei fehlt oder deren Klasse in der Datei nicht steht."""
    kaputt = []
    for z in ziele:
        datei, _, rest = z.partition("::")
        pfad = os.path.join(repo, *datei.split("/"))
        if not os.path.isfile(pfad):
            kaputt.append(f"{z} (Datei fehlt)")
            continue
        if rest:
            klasse = rest.split("::", 1)[0]
            with open(pfad, encoding="utf-8") as f:
                quelle = f.read()
            if not re.search(rf"^(class|def) {re.escape(klasse)}\b", quelle, re.M):
                kaputt.append(f"{z} ({klasse} nicht in {datei})")
    return kaputt


def _ci_text() -> str:
    with open(CI, encoding="utf-8") as f:
        return f.read()


def smoke_ziele(text: str) -> list[str]:
    jobs = ci_jobs(text)
    run = schritt_run(jobs.get(SMOKE_JOB, []), SMOKE_SCHRITT)
    return pytest_ziele(run or "")


_CI_MUSTER = """
name: CI
jobs:
  linux:
    runs-on: ubuntu-latest
    steps:
      - name: Unit-Tests ausfuehren
        run: python -m pytest tests/test_linux_only.py
  test:
    runs-on: windows-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Unit-Tests ausfuehren
        env:
          QT_QPA_PLATFORM: offscreen
        run: |
          python -m pytest tests/test_a.py tests/test_b.py::Klasse -v --tb=short
"""


class ParserTest(unittest.TestCase):
    """Der Parser selbst — sonst waere der Waechter unten trivial gruen."""

    def test_liest_genau_den_smoke_schritt_des_windows_jobs(self):
        self.assertEqual(smoke_ziele(_CI_MUSTER),
                         ["tests/test_a.py", "tests/test_b.py::Klasse"])

    def test_einzeiler_form(self):
        text = _CI_MUSTER.replace(
            "run: |\n          python -m pytest tests/test_a.py tests/test_b.py::Klasse"
            " -v --tb=short",
            "run: python -m pytest tests/test_c.py --tb short")
        self.assertEqual(smoke_ziele(text), ["tests/test_c.py"])

    def test_abdeckung_ueber_datei_oder_node_id(self):
        p = "tests/test_x.py::Klasse"
        self.assertTrue(deckt_ab(["tests/test_x.py"], p))
        self.assertTrue(deckt_ab([p], p))
        self.assertFalse(deckt_ab(["tests/test_x.py::Andere"], p))
        self.assertFalse(deckt_ab(["tests/test_x2.py"], p))

    def test_kaputtes_ziel_wird_gemeldet(self):
        self.assertEqual(
            kaputte_ziele(["tests/gibt_es_nicht.py",
                           "tests/test_ci_windows_legs.py::GibtEsNicht",
                           "tests/test_ci_windows_legs.py::ParserTest"]),
            ["tests/gibt_es_nicht.py (Datei fehlt)",
             "tests/test_ci_windows_legs.py::GibtEsNicht "
             "(GibtEsNicht nicht in tests/test_ci_windows_legs.py)"])


class WindowsSmokeTest(unittest.TestCase):
    """Der eigentliche Waechter — an der ECHTEN ci.yml."""

    def setUp(self):
        self.ziele = smoke_ziele(_ci_text())

    def test_smoke_schritt_gefunden(self):
        self.assertTrue(self.ziele, f"Schritt '{SMOKE_SCHRITT}' im Job "
                        f"'{SMOKE_JOB}' nicht gefunden oder ohne pytest-Ziele")

    def test_sandbox_tests_laufen_im_windows_smoke(self):
        fehlt = [p for p in PFLICHT_IM_SMOKE if not deckt_ab(self.ziele, p)]
        self.assertEqual(fehlt, [], "XPLAT-40: diese Sandbox-Tests fehlen im "
                         "Windows-Smoke — die Windows-Undichtigkeit (XPLAT-39) "
                         "faellt dann wieder erst am Rig auf.")

    def test_alle_smoke_ziele_existieren(self):
        self.assertEqual(kaputte_ziele(self.ziele), [])


if __name__ == "__main__":
    unittest.main()
