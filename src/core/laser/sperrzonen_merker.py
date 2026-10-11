"""LAS-32: „Auf diesem Rechner wurde schon einmal mit Sperrzonen gearbeitet."

Ein einziges Häkchen in ``ui_prefs.json`` (Schluessel
``sperrzonen_benutzt``). Davon haengt ab, ob das Hauptfenster die gelbe Zeile
„Laser gepatcht — keine Sperrzonen angelegt" zeigt
(:func:`src.core.laser.sperrzonen.kopfleisten_hinweis`): wer die Funktion nie
angefasst hat, bekommt keine Dauerwarnung.

Gesetzt wird es, wenn eine Zone angelegt oder eine Show mit Zonen geladen
wird. Es gehoert zum Rechner, nicht zur Show, und wird nie zurueckgenommen.
Nichts hier fasst die DMX-Ausgabe an.
"""
from __future__ import annotations

import json
import os

_SCHLUESSEL = "sperrzonen_benutzt"
_sitzung = False        # gilt fuer diese Sitzung, auch wenn das Schreiben scheitert


def _pfad() -> str:
    from src.core.paths import app_data_dir
    return os.path.join(app_data_dir(), "ui_prefs.json")


def _lies(pfad: str):
    """Inhalt als dict; ``{}`` wenn die Datei fehlt; ``None`` wenn sie da, aber
    unlesbar ist (dann wird sie NICHT ueberschrieben — fremde Abschnitte)."""
    if not os.path.exists(pfad):
        return {}
    try:
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:                                    # noqa: BLE001
        return None
    return daten if isinstance(daten, dict) else None


def war_benutzt(pfad: str | None = None) -> bool:
    if _sitzung:
        return True
    daten = _lies(pfad or _pfad())
    return bool(daten and daten.get(_SCHLUESSEL))


def merke_benutzt(pfad: str | None = None) -> None:
    global _sitzung
    if _sitzung:
        return
    _sitzung = True
    pfad = pfad or _pfad()
    try:
        daten = _lies(pfad)
        if daten is None or daten.get(_SCHLUESSEL):
            return
        daten[_SCHLUESSEL] = True
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        tmp = f"{pfad}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(daten, f, indent=2, ensure_ascii=False)
        os.replace(tmp, pfad)
    except Exception as e:                               # noqa: BLE001
        print(f"[sperrzonen] Merker nicht gespeichert: {e}")


def _vergiss_sitzung() -> None:
    """Nur fuer Tests."""
    global _sitzung
    _sitzung = False
