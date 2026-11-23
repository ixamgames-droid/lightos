"""DOC-10: Bilder fuer ``docs/anleitung_speed/`` (Speed-Dial, Tempo-Master).

Neu erzeugen: ``venv/bin/python tools/anleitungsbilder.py speed``.

Das Panel „Tempo-Speeds & Grand-Master“ war ein Handfoto vom 21.06.2026 und
zeigte noch den Knopf „Aktualisieren“ unter der Bus-Tabelle (seit BPM-08
entfallen) und keine Auto-Sync-Zeile. Die Szene legt genau die Busse an, die
die Anleitung beschreibt — ``Bass`` (Master 128), ``Drums`` (Sub von Bass, ½)
und ``Lead`` (Sub von Bass, 2×) — und raeumt sie danach wieder ab.
"""
from __future__ import annotations

from anleitungsbilder.runner import Szene, SzenenFehler

ZIEL = "docs/anleitung_speed/img"

_BUSSE = ("Bass", "Drums", "Lead")


def _mgr():
    from src.core.engine.tempo_bus import get_tempo_bus_manager
    return get_tempo_bus_manager()


def _ansicht(ui):
    view = getattr(ui.win, "_tempo_bus_view", None)
    if view is None:
        raise SzenenFehler("Tempo-Buses-Ansicht fehlt (BPM → Tempo-Buses)")
    return view


def _busse_anlegen(ui):
    mgr = _mgr()
    bass = mgr.ensure_bus("Bass")
    bass.set_role("master")
    bass.set_bpm(128.0)
    for name, faktor in (("Drums", 0.5), ("Lead", 2.0)):
        bus = mgr.ensure_bus(name)
        bus.set_role("sub")
        if not bus.set_parent(bass.bus_id):
            raise SzenenFehler(f"{name} laesst sich nicht an Bass haengen")
        bus.set_bus_multiplier(faktor)
    view = _ansicht(ui)
    view._refresh_speeds()
    ui.pump(0.2)
    # Die Tabelle zeigt nur rund fuenf Zeilen; die Busse A–D der Demo-Show
    # stehen davor. Drums waehlen (fuellt die Editor-Zeile: Sub, folgt Bass,
    # Faktor ½) und ans Ende rollen, damit Bass, Drums und Lead sichtbar sind.
    tabelle = view._bus_table
    for zeile in range(tabelle.rowCount()):
        zelle = tabelle.item(zeile, 0)
        if zelle is not None and zelle.text() == "Drums":
            tabelle.selectRow(zeile)
            break
    else:
        raise SzenenFehler("Bus „Drums“ fehlt in der Tabelle")
    tabelle.scrollToBottom()
    ui.pump(0.3)


def _busse_entfernen(ui):
    mgr = _mgr()
    for name in reversed(_BUSSE):
        if mgr.get(name) is not None:
            mgr.remove_bus(name)
    _ansicht(ui)._refresh_speeds()
    ui.pump(0.1)


def _panel(ui):
    from PySide6.QtWidgets import QGroupBox
    for box in _ansicht(ui).findChildren(QGroupBox):
        if box.isVisible() and box.title().replace("&&", "&").startswith(
                "Tempo-Speeds & Grand-Master"):
            return box
    raise SzenenFehler("Panel „Tempo-Speeds & Grand-Master“ nicht sichtbar")


SZENEN = [
    Szene("05_tempo_speeds", sektion="BPM", unterreiter="Tempo-Buses",
          vorher=_busse_anlegen, ausschnitt=_panel, nachher=_busse_entfernen,
          marken=[("Master anlegen", 1, "", "oben"),
                  ("Übernehmen", 2, "", "oben")],
          titel="Tempo-Speeds & Grand-Master: Bass (Master 128), Drums (½), "
                "Lead (2×)"),
]
