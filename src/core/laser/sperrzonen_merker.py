"""LAS-32: „Auf diesem Rechner wurde schon einmal mit Sperrzonen gearbeitet."

Ein einziges Häkchen in ``ui_prefs.json`` (Schluessel
``sperrzonen_benutzt``). Davon haengt ab, ob das Hauptfenster die gelbe Zeile
„Laser gepatcht — keine Sperrzonen angelegt" zeigt
(:func:`src.core.laser.sperrzonen.kopfleisten_hinweis`): wer die Funktion nie
angefasst hat, bekommt keine Dauerwarnung.

Gesetzt wird es, wenn eine Zone angelegt oder eine Show mit Zonen geladen
wird. Es gehoert zum Rechner, nicht zur Show, und wird nie zurueckgenommen.

Daneben, in derselben Datei: ob das Fenster „Sicht des Lasers" im 3D gezeigt
wird (Schluessel ``sperrzonen_lasersicht``, Vorgabe an) — eine reine
Anzeige-Vorliebe des Rechners.

Nichts hier fasst die DMX-Ausgabe an.
"""
from __future__ import annotations

import json
import os

_SCHLUESSEL = "sperrzonen_benutzt"
_sitzung = False        # gilt fuer diese Sitzung, auch wenn das Schreiben scheitert
_gelesen = None         # was die Datei beim ersten Nachsehen sagte (None = noch nicht)


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
    """Ohne ``pfad`` wird die Datei je Sitzung nur EINMAL gelesen: das
    Hauptfenster fragt im Takt seines NOT-AUS-Knopfs (gut zweimal je Sekunde),
    und ein Dateizugriff im UI-Thread gehoert dort nicht hin. Wahr werden kann
    die Antwort danach nur noch ueber :func:`merke_benutzt`."""
    global _gelesen
    if _sitzung:
        return True
    if pfad is not None:
        daten = _lies(pfad)
        return bool(daten and daten.get(_SCHLUESSEL))
    if _gelesen is None:
        daten = _lies(_pfad())
        _gelesen = bool(daten and daten.get(_SCHLUESSEL))
    return _gelesen


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


# ── Fenster „Sicht des Lasers" im 3D ────────────────────────────────────────
_SCHLUESSEL_LASERSICHT = "sperrzonen_lasersicht"
_lasersicht = None      # None = noch nicht nachgesehen


def lasersicht_zeigen(pfad: str | None = None) -> bool:
    """Soll das 3D das Fenster „Sicht des Lasers" zeigen? Vorgabe: ja. Ohne
    ``pfad`` wird die Datei je Sitzung nur einmal gelesen."""
    global _lasersicht
    if pfad is not None:
        daten = _lies(pfad)
        return bool(daten.get(_SCHLUESSEL_LASERSICHT, True)) if daten else True
    if _lasersicht is None:
        daten = _lies(_pfad())
        _lasersicht = bool(daten.get(_SCHLUESSEL_LASERSICHT, True)) if daten else True
    return _lasersicht


def merke_lasersicht(an: bool, pfad: str | None = None) -> None:
    """Gilt sofort fuer diese Sitzung, auch wenn das Schreiben scheitert."""
    global _lasersicht
    an = bool(an)
    eigener_pfad = pfad is not None
    if not eigener_pfad:
        if _lasersicht is an:
            return
        _lasersicht = an
    pfad = pfad or _pfad()
    try:
        daten = _lies(pfad)
        if daten is None or bool(daten.get(_SCHLUESSEL_LASERSICHT, True)) is an:
            return
        daten[_SCHLUESSEL_LASERSICHT] = an
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        tmp = f"{pfad}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(daten, f, indent=2, ensure_ascii=False)
        os.replace(tmp, pfad)
    except Exception as e:                               # noqa: BLE001
        print(f"[sperrzonen] Merker nicht gespeichert: {e}")


def _vergiss_sitzung() -> None:
    """Nur fuer Tests."""
    global _sitzung, _gelesen, _lasersicht
    _sitzung = False
    _gelesen = None
    _lasersicht = None
