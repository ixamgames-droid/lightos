#!/usr/bin/env python3
"""QA-72 — was weiss die Bibliothek ueber die HERKUNFT ihrer Profile?

Warum es dieses Werkzeug gibt
-----------------------------
``FixtureProfile.source`` sagt nur, durch welchen **Kanal** ein Profil hereinkam.
Der QXF-Importer stempelte darauf ``"qlcplus"`` — fuer **jede** eingelesene Datei,
unabhaengig davon, woher sie stammte. Gemessen am 2026-09-03 auf der gewachsenen
Bibliothek: **11 handgemachte Eigenbau-Profile** tragen dasselbe Etikett wie die
1730 echten QLC+-Definitionen, und ``source='user'`` — was Editor und Generator
eigentlich setzen — kommt **0-mal** vor. Erkennbar waren die Eigenbauten nur an
Tippfehlern und deutschen Kanalnamen.

Seit QA-72 traegt jedes importierte Profil zusaetzlich, was die **Quelldatei ueber
sich selbst sagt** (``<Creator>``-Block: Werkzeug, Version, Autor). Dieses
Werkzeug macht daraus einen Bericht — fuer den Bibliotheks-Durchgang, bei dem
entschieden wird, was mitgeliefert wird und was lokal bleibt (BACKLOG ``FM-42``),
und fuer die Namensnennung nach Apache-2.0 §4(c) (``PROC-11``).

★ **Was es NICHT kann, und das ist wichtig:** die Herkunft der Profile, die vor
QA-72 importiert wurden, ist **verloren** — die ``.qxf``-Dateien liegen nicht mehr
auf dem Rechner. Fuer sie steht hier „keine Angabe", und das heisst *nicht*
„selbstgebaut", sondern *„wir wissen es nicht"*. Wer aus dieser Spalte eine
Aussage ableiten will, muss neu importieren.

Aufruf::

    ./venv/bin/python tools/fixture_herkunft.py            # Bericht
    ./venv/bin/python tools/fixture_herkunft.py --autoren  # nur die Autorenliste
      (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _zeilen():
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine
    from src.core.database.models import FixtureProfile, Manufacturer
    with Session(engine()) as s:
        return s.execute(
            select(Manufacturer.name, FixtureProfile.name,
                   FixtureProfile.source, FixtureProfile.provenance)
            .join(FixtureProfile,
                  FixtureProfile.manufacturer_id == Manufacturer.id)).all()


def _autor(herkunft: str) -> str:
    """Der Autor aus ``"Werkzeug Version · Autor"`` — oder ``""``."""
    return herkunft.split(" · ", 1)[1].strip() if " · " in herkunft else ""


def bericht(zeilen, nur_autoren: bool = False) -> str:
    aus: list[str] = []
    if not nur_autoren:
        nach_kanal = collections.Counter(q or "(leer)" for _m, _n, q, _h in zeilen)
        aus.append(f"Profile gesamt: {len(zeilen)}")
        aus.append("")
        aus.append("Kanal (source) — wie das Profil hereinkam:")
        for kanal, n in nach_kanal.most_common():
            aus.append(f"  {kanal:12} {n:5}")

        mit = [z for z in zeilen if (z[3] or "").strip()]
        aus.append("")
        aus.append("Herkunft (provenance) — was die Quelldatei ueber sich sagt:")
        aus.append(f"  mit Angabe   {len(mit):5}")
        aus.append(f"  ohne Angabe  {len(zeilen) - len(mit):5}   "
                   "<- heisst NICHT 'selbstgebaut', sondern 'wir wissen es nicht'")
        if mit:
            aus.append("")
            aus.append("  Werkzeuge:")
            for werkzeug, n in collections.Counter(
                    (z[3] or "").split(" · ", 1)[0] for z in mit).most_common(10):
                aus.append(f"    {werkzeug[:60]:60} {n:5}")

    autoren = collections.Counter(
        a for a in (_autor(z[3] or "") for z in zeilen) if a)
    aus.append("")
    aus.append(f"Autoren (fuer die Namensnennung, PROC-11): {len(autoren)} verschiedene")
    for name, n in autoren.most_common():
        aus.append(f"  {name[:60]:60} {n:5}")
    if not autoren:
        aus.append("  (keine — alle Profile stammen aus der Zeit vor QA-72 "
                   "oder aus dem Quelltext)")
    return "\n".join(aus)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--autoren", action="store_true",
                   help="nur die Autorenliste (Namensnennung nach Apache-2.0)")
    args = p.parse_args()
    print(bericht(_zeilen(), nur_autoren=args.autoren))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
