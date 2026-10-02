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

QA-68: Daneben meldet es **Dubletten eines Builtin-Profils** — dasselbe
Modellkuerzel zweimal beim selben Hersteller, beide ``source='builtin'``. So lag
der ZQ06121 auf dem Windows-Rechner doppelt in der Bibliothek (Rest aus der Zeit
vor QA-54/QA-58), und vier Tests rissen an ``MultipleResultsFound``; einen
Test-Praefix trug keiner der beiden Eintraege. Eine frisch gebaute Bibliothek
legt jedes Builtin genau einmal an. Gleiches Kuerzel bei VERSCHIEDENEN
Herstellern (Martin/Showtec „Acrobat") ist keine Dublette.
Dubletten werden nur angezeigt, auch mit ``--entfernen``: welcher Eintrag bleibt,
entscheidet ein Mensch — Shows verweisen ueber ``fixture_profile_id`` auf genau
einen davon.
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


def builtin_dubletten(engine):
    """QA-68: ``[(hersteller, kuerzel, [(id, name, modi, raster), ...]), ...]``
    — je Hersteller und Modellkuerzel alle Builtin-Profile, sobald es mehr als
    eines sind. ``raster`` sagt, ob ein Modus eine Rastergeometrie traegt (der
    Rest auf dem Windows-Rechner war der Eintrag OHNE)."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session, selectinload
    from src.core.database.models import FixtureProfile

    gruppen: dict = {}
    with Session(engine) as s:
        abfrage = (select(FixtureProfile)
                   .where(FixtureProfile.source == "builtin")
                   .options(selectinload(FixtureProfile.manufacturer),
                            selectinload(FixtureProfile.modes))
                   .order_by(FixtureProfile.id))
        for p in s.scalars(abfrage):
            kuerzel = (p.short_name or p.name or "").strip()
            hersteller = p.manufacturer.name if p.manufacturer else "?"
            raster = any((m.grid_rows or 0) > 0 and (m.grid_cols or 0) > 0
                         for m in p.modes)
            gruppen.setdefault((p.manufacturer_id, kuerzel.casefold()),
                               (hersteller, kuerzel, []))[2].append(
                (p.id, p.name, len(p.modes), raster))
    return sorted((g for g in gruppen.values() if len(g[2]) > 1),
                  key=lambda g: (g[0].casefold(), g[1].casefold()))


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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--entfernen", action="store_true",
                   help="die gefundenen Test-Reste wirklich loeschen "
                        "(Builtin-Dubletten nie)")
    args = p.parse_args(argv)

    from src.core.database.fixture_db import engine as fdb_engine, DB_PATH
    eng = fdb_engine()
    hersteller, profile = finde(eng)
    dubletten = builtin_dubletten(eng)

    print(f"Bibliothek: {DB_PATH}")
    if dubletten:
        print(f"{len(dubletten)} Builtin-Profil(e) mehrfach beim selben Hersteller "
              f"(QA-68) — nur angezeigt, nie automatisch entfernt:")
        for name_h, kuerzel, eintraege in dubletten:
            print(f"  {name_h} / {kuerzel}:")
            for pid, name, modi, raster in eintraege:
                print(f"    Profil  id={pid}  {name!r}  {modi} Modi"
                      f"{'  mit Raster' if raster else ''}")
        print("  Vor dem Loeschen pruefen, welche id die Shows benutzen.\n")
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
    # XPLAT-20: Windows-Konsolen und -Pipes laufen ohne PYTHONUTF8 auf cp1252.
    # Die Statuszeichen dieses Werkzeugs (✓ ⚠ ★ ⏳) haben dort keine Abbildung,
    # der Bericht stirbt also mitten in der Ausgabe an einem UnicodeEncodeError.
    # Bewusst HIER und nicht auf Modulebene: beim Import (Tests laden die
    # Werkzeuge per exec_module) bleibt der Datenstrom des Aufrufers unberuehrt.
    for _strom in (sys.stdout, sys.stderr):
        if hasattr(_strom, "reconfigure"):
            _strom.reconfigure(encoding="utf-8")
    raise SystemExit(main())
