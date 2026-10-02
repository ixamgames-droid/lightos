"""FM-56: Werkzeug fuer die eigene Geraete-Bibliothek (LightOS-Profile).

Befehle (aus dem Repo-Root, mit dem venv-Python)::

    # alle Dateien unter fixtures/bibliothek/ pruefen (oder nur die genannten)
    python tools/bibliothek_profil.py pruefen [DATEI ...]

    # wohin gehoert eine Datei?
    python tools/bibliothek_profil.py pfad --hersteller "Stairville" --modell "LED PAR 56"

    # Profil aus der Fixture-DB als LightOS-Profil schreiben
    python tools/bibliothek_profil.py export --id 123 -o mein.json
    python tools/bibliothek_profil.py export --hersteller ADJ --modell "Dotz Matrix" -o x.json
    # ein eingebautes Profil (aus dem Quelltext, nicht aus der DB)
    python tools/bibliothek_profil.py export --builtin MH16 -o mh16.json

    # Datei als EIGENES Profil (source='user') in die Fixture-DB
    python tools/bibliothek_profil.py import mein.json [--db PFAD]

    # QLC+-Datei (.qxf) -> LightOS-Profil, Herkunft wird gesetzt
    python tools/bibliothek_profil.py qxf Stairville-LED-PAR-56.qxf --bibliothek

``--bibliothek`` schreibt an den richtigen Ort unter ``fixtures/bibliothek/``.
``--db`` waehlt eine andere fixtures.db als die eingestellte.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from src.core.database import bibliothek_format as BF  # noqa: E402


def _ausgabe(daten: dict, args) -> int:
    if getattr(args, "bibliothek", False):
        pfad = os.path.join(BF.BIBLIOTHEK_DIR, BF.dateiname(daten["hersteller"],
                                                            daten["modell"]))
        if os.path.exists(pfad) and not args.ueberschreiben:
            print(f"FEHLER: {os.path.relpath(pfad, REPO)} gibt es schon "
                  f"(--ueberschreiben)", file=sys.stderr)
            return 1
    else:
        pfad = args.o
    befunde = BF.pruefe(daten)
    if pfad and befunde:
        for b in befunde:
            print(f"FEHLER: {b}", file=sys.stderr)
        return 1
    if not pfad:
        sys.stdout.write(BF.als_json(daten))
        for b in befunde:
            print(f"BEFUND: {b}", file=sys.stderr)
        return 1 if befunde else 0
    BF.schreibe(daten, pfad)
    print(f"geschrieben: {pfad}")
    return 0


def _engine(args):
    from src.core.database.fixture_db import DB_PATH, get_engine
    # Bewusst get_engine statt engine(): kein ensure_builtins-Lauf, das
    # Werkzeug schreibt beim Lesen nichts in die Bibliothek.
    return get_engine(args.db or DB_PATH)


def _schreib_engine(args):
    """Engine fuer den EINEN schreibenden Befehl (``import``).

    ★ Review FM-56: eine neue, leere fixtures.db darf nicht mit nur dem
    importierten Profil entstehen — beim naechsten App-Start saehe
    ``_seed_if_empty`` einen Hersteller und liesse die Erstbefuellung aus (16
    Builtins fehlten dauerhaft). Deshalb wird eine leere DB hier zuerst
    befuellt, genau wie beim ersten Start der App."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database import fixture_db as FDB
    from src.core.database.models import Manufacturer
    eng = _engine(args)
    with Session(eng) as s:
        if s.execute(select(Manufacturer)).first() is None:
            FDB._seed(s)
            s.commit()
    return eng


def cmd_pruefen(args) -> int:
    if args.dateien:
        befunde = []
        for d in args.dateien:
            try:
                BF.lade_datei(d)
            except BF.ProfilFehler as e:
                befunde += e.befunde
    else:
        befunde = BF.pruefe_bibliothek(args.ordner)
        n = len(BF.bibliothek_dateien(args.ordner, mit_beispielen=True))
        print(f"{n} Datei(en) unter {args.ordner or BF.BIBLIOTHEK_DIR}")
    for b in befunde:
        print(f"FEHLER: {b}")
    print("OK" if not befunde else f"{len(befunde)} Befund(e)")
    return 1 if befunde else 0


def cmd_pfad(args) -> int:
    print(f"fixtures/bibliothek/{BF.dateiname(args.hersteller, args.modell)}")
    return 0


def cmd_export(args) -> int:
    if args.builtin:
        alle = BF.code_builtins_daten()
        if args.builtin not in alle:
            print(f"FEHLER: kein Builtin mit Kurzname {args.builtin!r} "
                  f"(vorhanden: {', '.join(sorted(alle))})", file=sys.stderr)
            return 1
        return _ausgabe(alle[args.builtin], args)
    eng = _engine(args)
    pid = args.id
    if pid is None:
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.database.models import (FixtureProfile, Manufacturer,
                                              MITGELIEFERT_QUELLEN)
        with Session(eng) as s:
            treffer = s.execute(
                select(FixtureProfile.id)
                .join(Manufacturer, FixtureProfile.manufacturer_id == Manufacturer.id)
                .where(Manufacturer.name == args.hersteller,
                       FixtureProfile.name == args.modell)
                .order_by(FixtureProfile.source.not_in(MITGELIEFERT_QUELLEN),
                          FixtureProfile.id)).scalars().all()
        if not treffer:
            print(f"FEHLER: {args.hersteller} / {args.modell} nicht in der Bibliothek",
                  file=sys.stderr)
            return 1
        pid = treffer[0]
    try:
        daten = BF.exportiere(pid, engine=eng)
    except (BF.ProfilFehler, ValueError) as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 1
    return _ausgabe(daten, args)


def cmd_import(args) -> int:
    try:
        pid = BF.importiere(args.datei, engine=_schreib_engine(args))
    except (BF.ProfilFehler, ValueError) as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 1
    print(f"angelegt: Profil {pid} (eigenes Profil)")
    return 0


def cmd_qxf(args) -> int:
    try:
        daten = BF.qxf_zu_daten(args.datei, original=args.original)
    except BF.ProfilFehler as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 1
    return _ausgabe(daten, args)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="befehl", required=True)

    a = sub.add_parser("pruefen", help="Dateien/Bibliothek pruefen")
    a.add_argument("dateien", nargs="*")
    a.add_argument("--ordner", help="anderer Bibliotheksordner")
    a.set_defaults(f=cmd_pruefen)

    a = sub.add_parser("pfad", help="Zielpfad fuer Hersteller + Modell")
    a.add_argument("--hersteller", required=True)
    a.add_argument("--modell", required=True)
    a.set_defaults(f=cmd_pfad)

    def ziel(a):
        a.add_argument("-o", metavar="DATEI", help="Zieldatei (sonst stdout)")
        a.add_argument("--bibliothek", action="store_true",
                       help="nach fixtures/bibliothek/<hersteller>/<modell>.json")
        a.add_argument("--ueberschreiben", action="store_true")

    a = sub.add_parser("export", help="Profil -> LightOS-Profil")
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", type=int)
    g.add_argument("--hersteller")
    g.add_argument("--builtin", metavar="KURZNAME")
    a.add_argument("--modell")
    a.add_argument("--db")
    ziel(a)
    a.set_defaults(f=cmd_export)

    a = sub.add_parser("import", help="Datei als eigenes Profil anlegen")
    a.add_argument("datei")
    a.add_argument("--db")
    a.set_defaults(f=cmd_import)

    a = sub.add_parser("qxf", help="QLC+-.qxf -> LightOS-Profil")
    a.add_argument("datei")
    a.add_argument("--original", help="Pfad in QLC+, z. B. resources/fixtures/X/Y.qxf")
    ziel(a)
    a.set_defaults(f=cmd_qxf)

    args = p.parse_args(argv)
    if args.befehl == "export" and args.hersteller and not args.modell:
        p.error("--hersteller braucht --modell")
    return args.f(args)


if __name__ == "__main__":
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
