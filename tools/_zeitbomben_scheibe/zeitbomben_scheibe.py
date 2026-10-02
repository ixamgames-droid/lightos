"""pytest-Plugin: nur jeden n-ten gesammelten Test ausfuehren (XPLAT-34).

Der Zeitbomben-Waechter (``tools/zeitbomben_gate.py``) verteilt seinen
Sammellauf auf mehrere Kindprozesse. Ganze DATEIEN zu verteilen reicht nicht:
``test_qa58_bibliothek_schema_unberuehrt.py`` braucht unter dem Uhrsprung allein
~31 s von ~47 s (gemessen 2026-10-02) — kein Kind waere schneller als diese eine
Datei. Deshalb sammelt jedes Kind ALLE Kandidaten und behaelt nur jeden n-ten
Test: ``LIGHTOS_ZEITBOMBEN_SCHEIBE=i/n`` -> Tests, deren Rang in der nach
Node-ID sortierten Liste ``k % n == i`` ist.

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
    # Verteilt wird nach dem Rang der stabilen Test-ID, NICHT nach der
    # Sammel-Reihenfolge (Review #865): jedes Kind ist ein eigener Prozess mit
    # eigenem Hash-Seed, und ein ``parametrize`` ueber eine Menge sammelt dort
    # in anderer Reihenfolge — nach Index verteilt liefen dann Tests doppelt
    # und andere gar nicht. Die Node-IDs sind in allen Kindern dieselben.
    rang = {id(t): r for r, t in enumerate(sorted(items, key=lambda t: t.nodeid))}
    behalten = [t for t in items if rang[id(t)] % n == i]
    weg = [t for t in items if rang[id(t)] % n != i]
    if weg:
        config.hook.pytest_deselected(items=weg)
    items[:] = behalten
