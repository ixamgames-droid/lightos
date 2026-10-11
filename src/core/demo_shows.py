"""DEMO-8: mitgelieferte Demo-Shows finden (Datei -> „Demo-Show öffnen").

Die Demo-Shows werden beim BAUEN erzeugt (``packaging/demo_shows.py``) und
liegen als ``demo_shows/`` bei den Programmdateien — im Windows-Setup unter
``C:\\Program Files\\LightOS\\_internal\\demo_shows`` und damit
SCHREIBGESCHUETZT, im Quellbetrieb im Repo (git-ignoriert, nur vorhanden, wenn
das Bau-Skript gelaufen ist).

Dieses Modul LIEST nur: das Verzeichnis ``demos.json`` (Datei, Titel,
Kurzbeschreibung) und, fuer den Selbsttest, ob jede genannte Datei eine Show
ist. Geoeffnet wird eine Demo vom Hauptfenster als neue, ungespeicherte Show
ohne Pfad — „Speichern" fuehrt zu „Speichern unter" im Show-Ordner des
Nutzers, das Original bleibt unberuehrt.
"""
from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass

from src.core.paths import programm_datei

#: Ordner unter ``programm_dir()`` und Name des Verzeichnisses darin — dieselben
#: Namen wie in ``packaging/demo_shows.py`` (das ``src`` bewusst nicht importiert).
ORDNER = "demo_shows"
INDEX = "demos.json"

#: Was im Quellbetrieb zu tun ist, wenn der Ordner fehlt.
BAU_HINWEIS = ("Keine Demo-Shows vorhanden. Im Quellbetrieb erzeugt sie "
               "„python packaging/demo_shows.py“ (unter einer Minute); "
               "das Windows-Setup bringt sie mit.")


@dataclass(frozen=True)
class DemoShow:
    schluessel: str
    titel: str
    beschreibung: str
    pfad: str

    @property
    def dateiname(self) -> str:
        return os.path.basename(self.pfad)


def ordner() -> str:
    """Der Demo-Ordner bei den Programmdateien (nur lesen!)."""
    return programm_datei(ORDNER)


def _index(basis: str) -> list[dict]:
    """Eintraege aus ``demos.json``; leer, wenn die Datei fehlt oder kaputt ist."""
    try:
        with open(os.path.join(basis, INDEX), encoding="utf-8") as f:
            daten = json.load(f)
    except (OSError, ValueError):
        return []
    eintraege = daten.get("demos") if isinstance(daten, dict) else None
    return [e for e in (eintraege or []) if isinstance(e, dict)]


def liste(basis: str | None = None) -> list[DemoShow]:
    """Die vorhandenen Demo-Shows in Menue-Reihenfolge.

    Nur Eintraege, deren Datei wirklich da ist; der Dateiname darf den Ordner
    nicht verlassen (kein ``..``, kein Unterordner) — ``demos.json`` ist eine
    Datei auf der Platte und wird nicht blind geglaubt.
    """
    basis = basis or ordner()
    aus: list[DemoShow] = []
    for e in _index(basis):
        datei = str(e.get("datei") or "")
        if not datei or datei != os.path.basename(datei) or not datei.endswith(".lshow"):
            continue
        pfad = os.path.join(basis, datei)
        if not os.path.isfile(pfad):
            continue
        titel = str(e.get("titel") or os.path.splitext(datei)[0])
        aus.append(DemoShow(schluessel=str(e.get("schluessel") or datei), titel=titel,
                            beschreibung=str(e.get("beschreibung") or ""), pfad=pfad))
    return aus


def pruefe(basis: str | None = None) -> list[str]:
    """Maengel des Demo-Ordners (leer = in Ordnung) — fuer den Selbsttest.

    Verlangt: ``demos.json`` lesbar, mindestens eine Demo, jede genannte Datei
    vorhanden und eine ``.lshow`` (ZIP mit ``show.json``).
    """
    basis = basis or ordner()
    rel = ORDNER + "/"
    if not os.path.isfile(os.path.join(basis, INDEX)):
        return [f"fehlt: {rel}{INDEX}"]
    eintraege = _index(basis)
    if not eintraege:
        return [f"{rel}{INDEX} nennt keine Demo-Show"]
    fehler = []
    vorhanden = {d.dateiname: d for d in liste(basis)}
    for e in eintraege:
        datei = str(e.get("datei") or "")
        demo = vorhanden.get(datei)
        if demo is None:
            fehler.append(f"fehlt: {rel}{datei or '(ohne Dateiname)'}")
            continue
        try:
            with zipfile.ZipFile(demo.pfad) as z:
                json.loads(z.read("show.json").decode("utf-8"))
        except Exception as ex:
            fehler.append(f"keine Show: {rel}{datei} ({type(ex).__name__})")
    return fehler
