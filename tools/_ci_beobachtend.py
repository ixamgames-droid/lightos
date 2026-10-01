"""XPLAT-41: CI-Checks, die nur beobachten — die EINE Liste fuer die Merge-Werkzeuge.

``continue-on-error: true`` auf Job-Ebene macht einen Job nur fuer den
Workflow-Status nicht blockierend. Sein Check-Run endet bei einem Fehlschlag
trotzdem mit ``conclusion=failure``, und solange er laeuft (bis zu
``timeout-minutes``), steht er als „laeuft noch" am PR. ``tools/pr_bereit.py``
und ``tools/pr_ci_status.py`` werten jeden Check-Run einzeln — ohne diese Liste
blockierte die beobachtende Leg also doch jeden Merge.

Die Werkzeuge zaehlen Checks aus :data:`BEOBACHTEND` weder als rot noch als
„laeuft noch", geben ihren Zustand aber als Hinweis aus.

Schluessel ist der ANZEIGENAME des Check-Runs, also das ``name:`` des Jobs in
``.github/workflows/ci.yml`` (ohne Matrix — mit Matrix haengte GitHub die
Matrixwerte an). ``tests/test_xplat41_ci_beobachtend.py`` prueft, dass jeder
Name einem Job mit ``continue-on-error: true`` entspricht: ein umbenannter Job
wuerde sonst still blockieren, ein scharf geschalteter still ignoriert.
Wer die Leg scharf schaltet, nimmt sie HIER heraus.
"""
from __future__ import annotations

#: Anzeigename des Check-Runs -> Kurzname fuer den Hinweis.
BEOBACHTEND: dict[str, str] = {
    "Windows-ARM64 — volle Suite (segmentiert, beobachtend)": "Windows-ARM64",
}

_GRUEN = {"SUCCESS", "SKIPPED", "NEUTRAL"}


def ist_beobachtend(name: str | None) -> bool:
    return (name or "").strip() in BEOBACHTEND


def zustand(status: str | None, ergebnis: str | None) -> str:
    """``gruen`` / ``rot`` / ``laeuft noch`` — fuer Check-Runs-API und Rollup.

    Die REST-API liefert kleingeschrieben (``completed``/``failure``), das
    Rollup von ``gh pr view`` gross — deshalb wird beides normalisiert.
    """
    e = (ergebnis or "").upper()
    if e in _GRUEN:
        return "gruen"
    if e:
        return "rot"
    if (status or "").upper() == "COMPLETED":
        return "rot"        # abgeschlossen ohne Ergebnis: im Zweifel rot
    return "laeuft noch"


def hinweis(beobachtet: list[tuple[str, str]]) -> str:
    """``beobachtend: Windows-ARM64 rot`` aus ``[(Name, Zustand), ...]``."""
    if not beobachtet:
        return ""
    teile = [f"{BEOBACHTEND.get(n, n)} {z}" for n, z in beobachtet]
    return "beobachtend (blockiert nicht): " + ", ".join(teile)
