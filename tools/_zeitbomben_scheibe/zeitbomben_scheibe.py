"""pytest-Plugin: nur jeden n-ten gesammelten Test ausfuehren (XPLAT-34).

Der Zeitbomben-Waechter (``tools/zeitbomben_gate.py``) verteilt seinen
Sammellauf auf mehrere Kindprozesse. Ganze DATEIEN zu verteilen reicht nicht:
``test_qa58_bibliothek_schema_unberuehrt.py`` braucht unter dem Uhrsprung allein
~31 s von ~47 s (gemessen 2026-10-02) — kein Kind waere schneller als diese eine
Datei. Deshalb sammelt jedes Kind ALLE Kandidaten und behaelt nur jeden n-ten
Test: ``LIGHTOS_ZEITBOMBEN_SCHEIBE=i/n`` -> Tests mit Index ``k % n == i``.

Bewusst in einem EIGENEN Ordner, nicht neben ``sitecustomize.py`` im
Uhr-Vorspann (``tools/_zeitsprung``): die Kanarienvogel-Tests geben dem Kind
absichtlich kaputte Vorspanne mit; dieses Plugin darf davon weder abhaengen noch
etwas an der Uhr aendern.
"""
import os

VAR = "LIGHTOS_ZEITBOMBEN_SCHEIBE"


def scheibe():
    """``(i, n)`` aus der Umgebung — ``None``, wenn nicht (gueltig) gesetzt."""
    wert = os.environ.get(VAR, "")
    try:
        i, n = (int(t) for t in wert.split("/"))
    except ValueError:
        return None
    return (i, n) if 0 <= i < n else None


def pytest_collection_modifyitems(config, items):
    s = scheibe()
    if s is None:
        return
    i, n = s
    behalten = [t for k, t in enumerate(items) if k % n == i]
    weg = [t for k, t in enumerate(items) if k % n != i]
    if weg:
        config.hook.pytest_deselected(items=weg)
    items[:] = behalten
