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

import os
import re
import stat

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_RUNNERS = ("tools/verify_loop.sh", "tools/verify_segmented.sh")

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


@pytest.mark.parametrize("rel", _RUNNERS)
def test_runner_exists_and_is_executable(rel):
    path = os.path.join(_REPO_ROOT, rel)
    assert os.path.isfile(path), (
        f"{rel} fehlt. Der Segment-Runner lag frueher ausserhalb des Repos — "
        "ein frischer Linux-Checkout hatte dadurch kein Gate fuer die volle Suite "
        "(XPLAT-11).")
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
