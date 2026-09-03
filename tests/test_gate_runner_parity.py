"""XPLAT-11 — beide Linux-Gate-Runner muessen dieselbe Umgebung setzen.

Es gibt zwei Wege, die Suite auf Linux zu fahren: ``tools/verify_loop.sh``
(ein Prozess bzw. Delegation an den Segment-Runner) und
``tools/verify_segmented.sh`` (ein Prozess pro Testdatei). Wenn die beiden
unterschiedliche Umgebungsvariablen setzen, misst man mit dem einen Runner etwas
anderes als mit dem anderen — und repariert Dinge, die im tatsaechlich benutzten
Gate gar nicht ankommen.

Genau das ist passiert: PR #470 (XPLAT-08) fuehrte ``LIGHTOS_HARDEN_EXIT`` in
``verify_loop.sh`` ein, der Segment-Runner lag aber ausserhalb des Repos und bekam
es nie. Ergebnis: das real benutzte Gate meldete 12 rote viz-Segmente, waehrend
``verify_loop.sh`` dieselben Dateien gruen sah. Der Fix aus #470 war korrekt und
kam trotzdem nie an.

Dieser Test nagelt die Umgebung an einer Stelle fest.
"""
from __future__ import annotations

import ast
import os
import re
import stat
import subprocess

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_RUNNERS = ("tools/verify_loop.sh", "tools/verify_segmented.sh")

# XPLAT-WIN (2026-08-04): dieselbe Zusicherung fuer die Windows-Kette. Sie hatte
# exakt die Drift, gegen die diese Datei auf Linux gebaut wurde — nur andersherum:
# die Gate-Umgebung stand AUSSERHALB des Repos (in Davids maschinenspezifischem
# ../run_tests.ps1), waehrend tools/verify_loop.ps1 gar nichts setzte. Ein
# frischer Windows-Checkout fuhr damit ein anderes Gate als der Entwicklungs-
# rechner, und LIGHTOS_HARDEN_EXIT fehlte dort vollstaendig.
_PS_RUNNERS = ("tools/verify_loop.ps1", "tools/verify_segmented.ps1")

# if (-not $env:NAME) { $env:NAME = "wert" }   — die PowerShell-Entsprechung zu
# `export NAME="${NAME:-wert}"`: setdefault, damit ein von aussen gesetzter Wert
# (etwa der des Lock-Runners) Vorrang behaelt.
_PS_SETDEFAULT = re.compile(
    r'^\s*if\s*\(\s*-not\s+\$env:(?P<name>[A-Z_][A-Z0-9_]*)\s*\)\s*\{\s*'
    r'\$env:(?P=name)\s*=\s*"(?P<value>[^"]*)"\s*\}', re.M)

# Variablen, die das Testverhalten aendern. Wer hier eine ergaenzt, muss sie in
# BEIDEN Runnern setzen — das ist der Sinn der Sache.
_GATE_VARS = ("QT_QPA_PLATFORM", "LIGHTOS_HARDEN_EXIT")

# export NAME="${NAME:-wert}"  bzw.  export NAME=${NAME:-wert}
_EXPORT = re.compile(
    r'^\s*export\s+(?P<name>[A-Z_][A-Z0-9_]*)='
    r'"?\$\{(?P=name):-(?P<value>[^}"]*)\}"?\s*$', re.M)


def _exports(rel_path: str) -> dict[str, str]:
    with open(os.path.join(_REPO_ROOT, rel_path), encoding="utf-8") as f:
        return {m.group("name"): m.group("value") for m in _EXPORT.finditer(f.read())}


def _git_index_mode(rel_path: str) -> str | None:
    """Der in Git hinterlegte Datei-Modus ("100755"/"100644") oder None.

    Das ist die Eigenschaft, auf die es ankommt: SIE reist in den Linux-Checkout,
    nicht das lokale Dateisystem-Bit.
    """
    try:
        erg = subprocess.run(["git", "ls-files", "-s", "--", rel_path],
                             cwd=_REPO_ROOT, capture_output=True, text=True,
                             timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if erg.returncode != 0 or not erg.stdout.strip():
        return None
    return erg.stdout.split()[0]


@pytest.mark.parametrize("rel", _RUNNERS)
def test_runner_exists_and_is_executable(rel):
    path = os.path.join(_REPO_ROOT, rel)
    assert os.path.isfile(path), (
        f"{rel} fehlt. Der Segment-Runner lag frueher ausserhalb des Repos — "
        "ein frischer Linux-Checkout hatte dadurch kein Gate fuer die volle Suite "
        "(XPLAT-11).")
    # ueber eine Variable statt direkt ``os.name``, sonst wertet Pyright den
    # jeweils anderen Zweig host-spezifisch als "unreachable" (dieselbe
    # Schreibweise wie in src/core/paths.py).
    plat = os.name
    if plat == "nt":
        # ⚠️ NICHT auf os.stat().st_mode zurueckbauen. NTFS kennt kein
        # Ausfuehrbar-Bit, Git setzt auf Windows core.filemode=false, und CPython
        # meldet fuer .sh-Dateien schlicht 0o666 -> S_IXUSR ist dort IMMER False.
        # Der Test war damit auf Windows unrettbar rot, obwohl die Dateien
        # korrekt als 100755 eingecheckt sind (XPLAT-WIN). Geprueft wird deshalb
        # der Git-Modus: genau der landet im Linux-Checkout, um den es geht.
        mode = _git_index_mode(rel)
        if mode is None:
            pytest.skip("kein Git-Checkout — Ausfuehrbar-Bit auf Windows nicht pruefbar")
        assert mode == "100755", (
            f"{rel} ist in Git als {mode} hinterlegt, nicht als 100755 — ein "
            "frischer Linux-Checkout bekommt die Datei damit nicht ausfuehrbar. "
            "Beheben mit: git update-index --chmod=+x " + rel)
    else:
        mode = os.stat(path).st_mode
        assert mode & stat.S_IXUSR, f"{rel} ist nicht ausfuehrbar (chmod +x)"


@pytest.mark.parametrize("var", _GATE_VARS)
def test_both_runners_set_the_same_gate_variable(var):
    values = {rel: _exports(rel).get(var) for rel in _RUNNERS}
    missing = [rel for rel, v in values.items() if v is None]
    assert not missing, (
        f"{var} wird nicht in allen Gate-Runnern gesetzt — fehlt in: {missing}. "
        "Genau diese Drift war XPLAT-11: die Exit-Haertung aus PR #470 landete nur "
        "in verify_loop.sh, weshalb das real benutzte Gate 12 Segmente rot meldete, "
        "die der andere Runner gruen sah. Erwartete Schreibweise: "
        f'export {var}="${{{var}:-wert}}"')
    distinct = set(values.values())
    assert len(distinct) == 1, (
        f"{var} hat je Runner einen anderen Default: {values}. Beide Gates muessen "
        "dasselbe messen.")


def _ps_setdefaults(rel_path: str) -> dict[str, str]:
    with open(os.path.join(_REPO_ROOT, rel_path), encoding="utf-8") as f:
        return {m.group("name"): m.group("value")
                for m in _PS_SETDEFAULT.finditer(f.read())}


@pytest.mark.parametrize("rel", _PS_RUNNERS)
def test_windows_runner_exists(rel):
    """Kein Ausfuehrbar-Bit noetig: .ps1 wird ueber `powershell -File` gestartet.

    Geprueft wird nur die Existenz — und die ist der Punkt: bis XPLAT-WIN gab es
    ``tools/verify_segmented.ps1`` gar nicht, die Segmentierung lag ausschliesslich
    im nicht-versionierten ``../run_tests.ps1``.
    """
    assert os.path.isfile(os.path.join(_REPO_ROOT, rel)), (
        f"{rel} fehlt. Ohne den Segment-Runner im Repo faehrt ein frischer "
        "Windows-Checkout die volle Suite in EINEM Prozess — genau die Variante, "
        "die an akkumulierendem Qt-Zustand stirbt (XPLAT-WIN).")


@pytest.mark.parametrize("var", _GATE_VARS)
def test_both_windows_runners_set_the_same_gate_variable(var):
    values = {rel: _ps_setdefaults(rel).get(var) for rel in _PS_RUNNERS}
    missing = [rel for rel, v in values.items() if v is None]
    assert not missing, (
        f"{var} wird nicht in allen Windows-Gate-Runnern gesetzt — fehlt in: "
        f"{missing}. Erwartete Schreibweise: "
        f'if (-not $env:{var}) {{ $env:{var} = "wert" }}')
    assert len(set(values.values())) == 1, (
        f"{var} hat je Windows-Runner einen anderen Default: {values}.")


@pytest.mark.parametrize("var", _GATE_VARS)
def test_windows_and_linux_gates_measure_the_same_thing(var):
    """Die eigentliche Zusicherung: beide PLATTFORMEN messen dasselbe.

    Ohne diesen Test koennten die vier Runner je Plattform in sich stimmig sein
    und trotzdem zwei verschiedene Gates ergeben — dann repariert man auf der
    einen Seite etwas, das auf der anderen gar nicht ankommt. Genau diese
    Verwechslung war XPLAT-11.
    """
    linux = _exports(_RUNNERS[0]).get(var)
    windows = _ps_setdefaults(_PS_RUNNERS[0]).get(var)
    # ⚠️ Ohne diese Zeile besteht der Test auch bei None == None — also genau
    # dann, wenn BEIDE Regexe nichts finden, etwa weil jemand die Schreibweise
    # umstellt. Ein Waechter, der bei kaputter Erkennung gruen wird, ist keiner.
    assert linux is not None and windows is not None, (
        f"{var} wurde in keinem der beiden Gates gefunden (linux={linux!r}, "
        f"windows={windows!r}) — vermutlich hat sich die Schreibweise geaendert "
        "und die Erkennung greift nicht mehr.")
    assert linux == windows, (
        f"{var}: Linux-Gate setzt {linux!r}, Windows-Gate {windows!r} — die "
        "beiden Plattformen messen damit Unterschiedliches.")


def test_windows_verify_loop_delegates_full_suite_to_the_segmented_runner():
    """Pendant zu ``test_verify_loop_delegates_full_suite_to_the_segmented_runner``.

    Ohne die Delegation faehrt ein ``verify_loop.ps1`` ohne Lock-Runner die Suite
    in EINEM ``pytest tests/``-Prozess — die Variante, gegen die es den
    Segment-Runner ueberhaupt gibt.
    """
    with open(os.path.join(_REPO_ROOT, "tools/verify_loop.ps1"), encoding="utf-8") as f:
        src = f.read()
    assert "verify_segmented.ps1" in src, (
        "tools/verify_loop.ps1 delegiert die volle Suite nicht an "
        "tools/verify_segmented.ps1 (XPLAT-WIN).")


def test_verify_loop_delegates_full_suite_to_the_segmented_runner():
    """Die volle Suite gehoert auf Linux in den Segment-Runner.

    Pendant zu Windows, wo ``verify_loop.ps1`` fuer die volle Suite an
    ``run_tests.ps1 -Isolate`` delegiert. Gezielte Einzeldateien laufen weiterhin
    direkt — dort gibt es keinen akkumulierenden Zustand zu vermeiden.
    """
    with open(os.path.join(_REPO_ROOT, "tools/verify_loop.sh"), encoding="utf-8") as f:
        src = f.read()
    assert "verify_segmented.sh" in src, (
        "tools/verify_loop.sh delegiert die volle Suite nicht an "
        "tools/verify_segmented.sh (XPLAT-11). Ohne Delegation faehrt ein "
        "'./tools/verify_loop.sh' ohne Argumente die Suite in EINEM Prozess — "
        "genau die Variante, die auf Linux an akkumulierendem Qt-Zustand starb.")


# ── XPLAT-26: beide Gates muessen denselben UMFANG kompilieren ───────────────
#
# Die Umgebungs-Pruefungen oben nageln fest, dass beide Runner dasselbe MESSEN.
# Der Syntax-Check davor lief trotzdem auseinander: `verify_loop.sh` kompiliert
# seit QA-51(e) `src` UND `tools`, `verify_loop.ps1` nur `src`. Ein Syntaxfehler
# in einem Werkzeug fiel auf Windows also durch — besonders unangenehm bei
# `gen_tools_index.py`, das einen SyntaxError beim Einlesen in die harmlose
# Index-Zelle "(Docstring nicht lesbar)" verwandelt: die kaputte Datei erscheint
# ordentlich im Verzeichnis, und der Index bestaetigt sie sogar.
_COMPILEALL = "compileall -q "


def _compileall_umfang(rel_path: str) -> list[str] | None:
    """Die Verzeichnisse hinter ``compileall -q`` — aus dem ECHTEN Skript gelesen.

    Bewusst kein Nachbau der Aufruflogik: geprueft werden soll, was die Datei
    sagt, nicht was der Test glaubt.
    """
    with open(os.path.join(_REPO_ROOT, rel_path), encoding="utf-8") as f:
        for zeile in f:
            if _COMPILEALL not in zeile or zeile.lstrip().startswith("#"):
                continue
            rest = zeile.split(_COMPILEALL, 1)[1]
            for trenner in (";", "#", "|", ")"):
                rest = rest.split(trenner, 1)[0]
            teile = [t for t in rest.split() if not t.startswith("-")]
            if teile:
                return teile
    return None


def test_beide_gates_kompilieren_denselben_umfang():
    linux = _compileall_umfang("tools/verify_loop.sh")
    windows = _compileall_umfang("tools/verify_loop.ps1")
    # ⚠ Ohne diese Zeile besteht der Test auch bei None == None — also genau
    # dann, wenn die Erkennung in BEIDEN Dateien nichts findet.
    assert linux and windows, (
        f"compileall-Aufruf nicht gefunden (linux={linux!r}, windows={windows!r}) "
        "— vermutlich hat sich die Schreibweise geaendert.")
    assert linux == windows, (
        f"Die Gates kompilieren Unterschiedliches: Linux {linux}, Windows "
        f"{windows}. Ein Syntaxfehler in einem nur auf einer Seite geprueften "
        "Verzeichnis faellt dort durch (XPLAT-26).")
    assert "tools" in linux, (
        "Kein Gate kompiliert `tools` — dann faellt ein Syntaxfehler in einem "
        "Werkzeug erst auf, wenn jemand es benutzt (QA-51(e)).")


# ── XPLAT-23: die Querverweise der Linux-Gate-Tests duerfen nicht verrotten ──
#
# Die vier Linux-Gate-Testdateien ueberspringen auf Windows — zu Recht, sie
# pruefen flock, /proc und bash. Was sie NICHT tun duerfen, ist den Leser im
# Unklaren lassen: bis XPLAT-23 stand in ihren Skip-Gruenden "ohne flock gibt es
# bewusst keine Sperre", und das war seit Scheibe 1 schlicht falsch — Windows
# hat eine. Wer das las, hielt den Windows-Runner fuer ungeschuetzt.
#
# ★ Die Skip-Gruende nennen deshalb jetzt die Datei, die dieselbe Zusicherung
# auf der anderen Plattform am Verhalten prueft. Ein Querverweis, den niemand
# nachhaelt, ist aber schlimmer als keiner: benennt jemand die Zieldatei um,
# steht in 40 Skip-Meldungen ein Verweis ins Leere. Dieser Test haelt das fest.
_GATE_TESTS_MIT_QUERVERWEIS = (
    "tests/test_verify_loop_sperre.py",
    "tests/test_gate_webengine_lane.py",
    "tests/test_proc02c_webengine_sperre.py",
    "tests/test_proc02d_volle_suite_fd9.py",
)
_VERWEIS = re.compile(r"tests/test_[A-Za-z0-9_]+\.py")


def _skip_gruende(rel_path: str) -> list[str]:
    """Die Texte, die als Skip-Grund vor dem Leser landen — und nur die.

    ⚠ Eine simple Textsuche ueber die ganze Datei taugt nicht: `proc02d`
    SCHREIBT Dateinamen wie ``tests/test_enkel.py`` in ein Wegwerf-Repo, und
    die sahen wie Querverweise aus (beim Bau dieses Waechters prompt als
    Fehlalarm aufgeschlagen). Geprueft werden deshalb nur String-Konstanten,
    die auf ``GRUND`` enden, und String-Literale in ``skipUnless``/``skipIf``.
    """
    with open(os.path.join(_REPO_ROOT, rel_path), encoding="utf-8") as f:
        baum = ast.parse(f.read())
    texte: list[str] = []

    def sammle(knoten):
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            texte.append(knoten.value)
        elif isinstance(knoten, ast.BinOp):
            sammle(knoten.left); sammle(knoten.right)
        elif isinstance(knoten, ast.JoinedStr):
            for teil in knoten.values:
                sammle(teil)

    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Assign):
            for ziel in knoten.targets:
                if isinstance(ziel, ast.Name) and ziel.id.endswith("GRUND"):
                    sammle(knoten.value)
        elif isinstance(knoten, ast.Call):
            name = getattr(knoten.func, "attr", getattr(knoten.func, "id", ""))
            if name in ("skipUnless", "skipIf"):
                for arg in knoten.args[1:]:
                    sammle(arg)
    return texte


def test_die_querverweise_der_gate_tests_zeigen_auf_vorhandene_dateien():
    fehlend = []
    gefunden = 0
    for rel in _GATE_TESTS_MIT_QUERVERWEIS:
        assert os.path.isfile(os.path.join(_REPO_ROOT, rel)), f"{rel} fehlt"
        for text in _skip_gruende(rel):
            for ziel in set(_VERWEIS.findall(text)):
                if ziel == rel:
                    continue                  # Selbstnennung, kein Verweis
                gefunden += 1
                if not os.path.isfile(os.path.join(_REPO_ROOT, ziel)):
                    fehlend.append(f"{rel} -> {ziel}")
    assert not fehlend, (
        "Skip-Gruende verweisen auf Dateien, die es nicht (mehr) gibt: "
        f"{fehlend}. Dann steht in den uebersprungenen Meldungen ein Hinweis "
        "ins Leere — und der Leser auf der anderen Plattform weiss wieder "
        "nicht, ob die Zusicherung dort ueberhaupt geprueft wird.")
    # ⚠ Ohne diese Zeile waere der Test auch dann gruen, wenn die Verweise
    # komplett verschwaenden — genau die Falle aus QA-52.
    assert gefunden >= 4, (
        f"nur {gefunden} Querverweise in Skip-Gruenden gefunden — vermutlich "
        "sind die Hinweise auf das jeweils andere Gate verschwunden.")

# ── PROC-04: dieselbe Zusicherung fuer die BEIDEN CI-Legs ────────────────────
#
# Die Datei oben nagelt die Umgebung der zwei Linux-RUNNER fest. Dieselbe Drift
# gab es eine Ebene hoeher, zwischen den zwei CI-JOBS: die Exit-Haertung
# (`LIGHTOS_HARDEN_EXIT_ALL`) stand nur in der Windows-Leg. Auf Linux griff
# damit nur der enge Weg — `armed and LIGHTOS_HARDEN_EXIT`, und `armed` wird
# ausschliesslich fuer WebEngine-Module gesetzt. Ein gewoehnlicher Qt-View-Test
# starb im nativen Abbau mit SIGSEGV, das Segment meldete `exit 139` bei LEERER
# Liste fehlgeschlagener Tests, und der Lauf wurde faelschlich rot.
#
# PyYAML ist in dieser Umgebung nicht installiert, und ein Waechter, der eine
# Abhaengigkeit mitbringt, wird nicht gefahren. Der Parser unten liest deshalb
# nur die eine Form, um die es geht: die Job-Bloecke unter `jobs:`, an der
# Einrueckung erkannt.

_HAERTUNG = "LIGHTOS_HARDEN_EXIT_ALL"


def ci_jobs(text: str) -> dict[str, str]:
    """``{Job-Name: Rohtext des Blocks}`` fuer alles unter ``jobs:``."""
    zeilen = text.splitlines()
    start = None
    for i, z in enumerate(zeilen):
        if z.rstrip() == "jobs:":
            start = i + 1
            break
    if start is None:
        return {}
    jobs: dict[str, list[str]] = {}
    aktuell = None
    for z in zeilen[start:]:
        if z.strip() and not z.startswith(" "):
            break                       # naechster Top-Level-Schluessel
        gestrippt = z.strip()
        if (len(z) - len(z.lstrip(" "))) == 2 and gestrippt.endswith(":") \
                and not gestrippt.startswith("#") and ": " not in gestrippt:
            aktuell = gestrippt[:-1]
            jobs[aktuell] = []
            continue
        if aktuell is not None:
            jobs[aktuell].append(z)
    return {k: "\n".join(v) for k, v in jobs.items()}


def jobs_ohne_haertung(text: str) -> list[str]:
    return [name for name, block in ci_jobs(text).items()
            if _HAERTUNG not in block]


_CI_BEIDE = """
name: CI
on:
  push:
jobs:
  linux:
    runs-on: ubuntu-latest
    steps:
      - name: Suite
        env:
          LIGHTOS_HARDEN_EXIT_ALL: "1"
        run: ./tools/verify_loop.sh
  test:
    runs-on: windows-latest
    steps:
      - name: Suite
        env:
          LIGHTOS_HARDEN_EXIT_ALL: "1"
        run: pytest
"""

_CI_NUR_WINDOWS = _CI_BEIDE.replace(
    """      - name: Suite
        env:
          LIGHTOS_HARDEN_EXIT_ALL: "1"
        run: ./tools/verify_loop.sh""",
    """      - name: Suite
        run: ./tools/verify_loop.sh""")


def test_beide_ci_legs_haerten_den_exit_gleich():
    """Der eigentliche Waechter — an der ECHTEN ci.yml."""
    with open(os.path.join(_REPO_ROOT, ".github", "workflows", "ci.yml"),
              encoding="utf-8") as f:
        text = f.read()
    fehlt = jobs_ohne_haertung(text)
    assert fehlt == [], (
        f"CI-Jobs ohne {_HAERTUNG}: {fehlt}. Ohne die Variable greift die "
        "Exit-Haertung nur fuer WebEngine-Sessions; ein gewoehnlicher "
        "Qt-View-Test stirbt im nativen Abbau mit SIGSEGV und macht den Lauf "
        "faelschlich rot (PROC-04, exit 139 bei leerer FAILED-Liste).")


def test_die_echte_ci_hat_ueberhaupt_zwei_jobs():
    """Ohne das waere der Waechter oben trivial gruen: keine Jobs, keine Luecken."""
    with open(os.path.join(_REPO_ROOT, ".github", "workflows", "ci.yml"),
              encoding="utf-8") as f:
        jobs = ci_jobs(f.read())
    assert len(jobs) >= 2, f"nur {len(jobs)} Job(s) erkannt: {sorted(jobs)}"
    assert "linux" in jobs


def test_fehlende_haertung_wird_beanstandet():
    assert jobs_ohne_haertung(_CI_NUR_WINDOWS) == ["linux"]


def test_vollstaendige_haertung_wird_nicht_beanstandet():
    # Positivkontrolle: ein Waechter, der auch den gesunden Fall beanstandet,
    # zwingt zu einer Angabe, die nichts bewirkt — und wird abgeschaltet.
    assert jobs_ohne_haertung(_CI_BEIDE) == []
