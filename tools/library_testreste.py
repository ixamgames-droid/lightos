#!/usr/bin/env python3
"""Findet (und entfernt auf Wunsch) Test-Rueckstaende in der Fixture-Bibliothek.

QA-54: Bis zum 2026-08-11 legten Tests ihre Profile in der ECHTEN Bibliothek an
(``LIGHTOS_FIXTURE_DB`` zeigte damals auf die reale ``fixtures.db``, damit Tests
gegen die reale Library laufen; seit QA-58 ist es eine prozess-eigene KOPIE
davon). Der Aufraeumschritt loeschte das
Profil, den ueber ``_get_or_create_mfr`` angelegten **Hersteller** aber nie — er
steht seither in der Herstellerliste des Patch-Dialogs.

Die Ursache ist behoben (``test_spider_dual_tilt_marker.py`` baut sich jetzt
eine eigene temporaere Bibliothek). Was bereits in der Datei steht, raeumt
dieses Werkzeug.

★ **Es loescht NICHTS ohne ``--entfernen``.** Die Bibliothek sind Nutzerdaten:
dort ungefragt aufzuraeumen ist keine Hygiene, sondern ein Eingriff. Der
Default zeigt nur an, was gefunden wurde.

    python3 tools/library_testreste.py               # nur anzeigen
    python3 tools/library_testreste.py --entfernen   # wirklich loeschen

Erkannt wird, was den Test-Praefix traegt — bewusst eng: ein Hersteller, der
zufaellig „Test" heisst, ist ein Nutzerprofil und geht dieses Werkzeug nichts an.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Bewusst eng: nur was die Tests nachweislich anlegen. Alles Weitere waere
# Raten auf fremden Daten.
_TEST_PRAEFIXE = ("TEST-DualTilt", "TEST Speider", "TEST QLC Speider")


def _passt(name: str) -> bool:
    return any(name.startswith(p) for p in _TEST_PRAEFIXE)


def finde(engine):
    """(hersteller, profile) — je Liste von (id, name)."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.models import Manufacturer, FixtureProfile

    with Session(engine) as s:
        hersteller = [(m.id, m.name) for m in s.scalars(select(Manufacturer))
                      if _passt(m.name or "")]
        profile = [(p.id, p.name) for p in s.scalars(select(FixtureProfile))
                   if _passt(p.name or "")]
    return hersteller, profile


def entferne(engine, hersteller, profile) -> int:
    from sqlalchemy.orm import Session
    from src.core.database.models import Manufacturer, FixtureProfile

    n = 0
    with Session(engine) as s:
        for pid, _ in profile:
            obj = s.get(FixtureProfile, pid)
            if obj is not None:
                s.delete(obj)       # cascade -> Modi/Kanaele/Ranges
                n += 1
        for mid, _ in hersteller:
            obj = s.get(Manufacturer, mid)
            # Nur loeschen, wenn kein Profil mehr daran haengt — sonst risse
            # das Werkzeug einem echten Profil den Hersteller weg.
            if obj is not None and not getattr(obj, "fixtures", None):
                s.delete(obj)
                n += 1
        s.commit()
    return n


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--entfernen", action="store_true",
                   help="die gefundenen Reste wirklich loeschen")
    args = p.parse_args()

    from src.core.database.fixture_db import engine as fdb_engine, DB_PATH
    eng = fdb_engine()
    hersteller, profile = finde(eng)

    print(f"Bibliothek: {DB_PATH}")
    if not hersteller and not profile:
        print("Keine Test-Rueckstaende gefunden.")
        return 0
    for mid, name in hersteller:
        print(f"  Hersteller  id={mid}  {name!r}")
    for pid, name in profile:
        print(f"  Profil      id={pid}  {name!r}")
    if not args.entfernen:
        print(f"\n{len(hersteller) + len(profile)} Rueckstand/Rueckstaende. "
              f"Zum Loeschen: --entfernen")
        return 0
    n = entferne(eng, hersteller, profile)
    print(f"\n{n} Eintraege entfernt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
