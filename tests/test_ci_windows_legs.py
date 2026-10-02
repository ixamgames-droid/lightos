"""Waechter: was die Windows-Legs der CI wirklich fahren (XPLAT-40, XPLAT-41).

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

XPLAT-41 ergaenzt eine Windows-ARM64-Leg (Job ``windows-arm``), die zunaechst
NICHT blockiert. Der Waechter haelt ihre Eckdaten fest: echter ARM-Runner,
der segmentierte Runner mit einem Parameter, den ``tools/verify_segmented.ps1``
wirklich kennt, ein Timeout, und ``continue-on-error``, solange die Leg nur
beobachtet.

XPLAT-45 dreht die Python-Architektur der SUITE um: x64 unter Emulation statt
nativem ARM64. Die win_arm64-Wheels von PySide6-Addons enthalten kein
QtWebEngine (gemessen 6.11.2: Leg flaechig rot, ~90 Visualizer-Dateien); der
echte ARM-Rechner laeuft genau deshalb mit x64-Python. Natives ARM64 bleibt
als Befund-Schritt (``tools/qt_module_befund.py``) im Job — VOR der x64-Stufe,
denn die zuletzt eingerichtete Python-Version steht vorne im PATH und baut das
``venv/`` der Suite.

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


ARM_JOB = "windows-arm"
SEGMENT_PS1 = os.path.join(REPO, "tools", "verify_segmented.ps1")


def job_schluessel(job_zeilen: list[str], schluessel: str) -> str | None:
    """Wert eines Schluessels direkt auf Job-Ebene (Einrueckung 4)."""
    for z in job_zeilen:
        if _einrueckung(z) == 4 and z.strip().startswith(schluessel + ":"):
            return z.strip()[len(schluessel) + 1:].split(" #", 1)[0].strip().strip("'\"")
    return None


def with_werte(job_zeilen: list[str], action: str) -> dict[str, str]:
    """``with:``-Werte des ersten Schritts, der ``action`` benutzt."""
    alle = alle_with_werte(job_zeilen, action)
    return alle[0] if alle else {}


def alle_with_werte(job_zeilen: list[str], action: str) -> list[dict[str, str]]:
    """``with:``-Werte JEDES Schritts, der ``action`` benutzt, in Reihenfolge."""
    ergebnis = []
    for i, z in enumerate(job_zeilen):
        if "uses:" not in z or action not in z:
            continue
        tiefe = _einrueckung(z)
        werte, im_with = {}, False
        for zj in job_zeilen[i + 1:]:
            if not zj.strip() or zj.lstrip().startswith("#"):
                continue
            t = _einrueckung(zj)
            if t < tiefe or (t == tiefe - 2 and zj.lstrip().startswith("- ")):
                break
            if t == tiefe:
                im_with = zj.strip() == "with:"
                continue
            if im_with and t > tiefe:
                k, _, v = zj.strip().partition(":")
                werte[k] = v.split(" #", 1)[0].strip().strip("'\"")
        ergebnis.append(werte)
    return ergebnis


def ps1_parameter(pfad: str = SEGMENT_PS1) -> set[str]:
    """Namen + Aliase aus dem ``param(...)``-Block, klein geschrieben."""
    with open(pfad, encoding="utf-8") as f:
        quelle = f.read()
    m = re.search(r"^param\((.*?)^\)", quelle, re.M | re.S)
    if not m:
        return set()
    block = m.group(1)
    namen = {n.lower() for n in re.findall(r"\$(\w+)", block)}
    for aliase in re.findall(r"\[Alias\(([^)]*)\)\]", block):
        namen |= {a.strip().strip("'\"").lower() for a in aliase.split(",")}
    return namen


def segment_aufrufe(job_zeilen: list[str]) -> list[list[str]]:
    """Argumente jedes ``verify_segmented.ps1``-Aufrufs im Job."""
    aufrufe = []
    for z in job_zeilen:
        if "verify_segmented.ps1" not in z or z.lstrip().startswith("#"):
            continue
        teile = z.strip().split()
        ab = next(i for i, t in enumerate(teile) if "verify_segmented.ps1" in t) + 1
        aufrufe.append(teile[ab:])
    return aufrufe


def unbekannte_schalter(argumente: list[str], bekannt: set[str]) -> list[str]:
    return [a for a in argumente
            if a.startswith("-") and a[1:].lower() not in bekannt]


class WindowsArmParserTest(unittest.TestCase):
    _MUSTER = """
jobs:
  windows-arm:
    runs-on: windows-11-arm
    timeout-minutes: 90
    continue-on-error: true  # beobachtet nur
    steps:
      - name: Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.14"
          architecture: arm64
      - name: Suite
        run: pwsh tools/verify_segmented.ps1 -j 4
"""

    def test_liest_job_eckdaten(self):
        job = ci_jobs(self._MUSTER)[ARM_JOB]
        self.assertEqual(job_schluessel(job, "runs-on"), "windows-11-arm")
        self.assertEqual(job_schluessel(job, "continue-on-error"), "true")
        self.assertEqual(job_schluessel(job, "timeout-minutes"), "90")
        self.assertEqual(with_werte(job, "actions/setup-python"),
                         {"python-version": "3.14", "architecture": "arm64"})
        self.assertEqual(segment_aufrufe(job), [["-j", "4"]])

    def test_param_block_des_echten_skripts(self):
        p = ps1_parameter()
        self.assertIn("jobs", p)
        self.assertIn("j", p)
        self.assertNotIn("parallel", p)

    def test_unbekannter_schalter_wird_gemeldet(self):
        self.assertEqual(unbekannte_schalter(["-Parallel", "4", "-j", "4"],
                                             {"jobs", "j"}), ["-Parallel"])


class WindowsArmJobTest(unittest.TestCase):
    """XPLAT-41 — an der ECHTEN ci.yml."""

    def setUp(self):
        self.job = ci_jobs(_ci_text()).get(ARM_JOB)
        self.assertIsNotNone(self.job, f"Job '{ARM_JOB}' fehlt in ci.yml")

    def test_laeuft_auf_echtem_arm_runner(self):
        self.assertEqual(job_schluessel(self.job, "runs-on"), "windows-11-arm")

    def test_suite_mit_x64_python_wie_am_rig(self):
        # XPLAT-45: die ZULETZT eingerichtete Python-Version steht vorne im
        # PATH und baut venv/ — sie muss x64 sein, sonst fehlt QtWebEngine.
        stufen = alle_with_werte(self.job, "actions/setup-python")
        self.assertTrue(stufen, "kein setup-python im Job")
        self.assertEqual(stufen[-1].get("architecture"), "x64",
                         "natives ARM64 hat kein QtWebEngine (win_arm64-Wheels) — "
                         "die Suite waere flaechig rot")
        for py in stufen:
            self.assertTrue(py.get("python-version", "").startswith("3."), py)

    def test_natives_arm64_bleibt_als_befund(self):
        stufen = alle_with_werte(self.job, "actions/setup-python")
        archs = [py.get("architecture") for py in stufen]
        self.assertIn("arm64", archs[:-1],
                      "der Befund zu den nativen ARM64-Wheels fehlt")
        text = "\n".join(self.job)
        self.assertIn("tools/qt_module_befund.py", text)
        self.assertTrue(os.path.isfile(os.path.join(REPO, "tools", "qt_module_befund.py")))

    def test_faehrt_den_segmentierten_runner_mit_gueltigen_schaltern(self):
        aufrufe = segment_aufrufe(self.job)
        self.assertTrue(aufrufe, "verify_segmented.ps1 wird nicht aufgerufen")
        bekannt = ps1_parameter()
        for args in aufrufe:
            self.assertEqual(unbekannte_schalter(args, bekannt), [], args)

    def test_beobachtet_nur_und_hat_ein_timeout(self):
        # Solange XPLAT-41 nicht ausgewertet ist, darf die Leg keinen PR
        # blockieren. Wer sie scharf schaltet, passt diesen Test bewusst an.
        self.assertEqual(job_schluessel(self.job, "continue-on-error"), "true")
        t = job_schluessel(self.job, "timeout-minutes")
        self.assertTrue(t and t.isdigit() and 0 < int(t) <= 180, t)


if __name__ == "__main__":
    unittest.main()
