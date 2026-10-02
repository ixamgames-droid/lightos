"""TOOL-3: Geraeteprofil ueber Hersteller + Modell aufloesen — nie ueber eine rohe ID.

Eine Profil-ID ist eine SQLite-Auto-ID und damit rechnerabhaengig: eine anders
gewachsene Fixture-Bibliothek vergibt andere Nummern.
``build_spot90_testshow.py`` trug die rohe ID 1698 — auf jedem Rechner mit
einer anderen Bibliothek zeigte sie auf ein anderes Geraet (oder ins Leere),
und das Werkzeug merkte es nicht. Hier wird ueber den Namen aufgeloest, und
fehlt das Geraet oder der Modus, endet der Lauf LAUT (``SystemExit``) mit dem,
was gesucht wurde und was es stattdessen gibt.

Bei Mehrdeutigkeit gilt dieselbe Reihenfolge wie beim Laden einer Show
(``show_file._resolve_fixture_profile_id``, FM-43): ``source='builtin'`` zuerst,
dann nach ID — gemeldet, nicht verschwiegen.

Verwendung in einem Generator (nach dem ``src``-Pfad-Setup)::

    from _profil import profil_id
    PID = profil_id("Varytec", "Hero Spot 90", modus="16 Channel", kanaele=16)
"""
from __future__ import annotations


def profil_id(hersteller: str, modell: str, *, modus: str | None = None,
              kanaele: int | None = None) -> int:
    """ID des Profils ``hersteller`` / ``modell`` in der aktuellen Bibliothek.

    ``modus`` (und ``kanaele``) werden mitgeprueft, wenn angegeben: ein Profil,
    das den erwarteten Modus nicht hat, ist fuer den Generator so falsch wie
    ein fehlendes.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from src.core.database.fixture_db import engine
    from src.core.database.models import FixtureMode, FixtureProfile, Manufacturer

    geraet = f"{hersteller} / {modell}"
    with Session(engine()) as s:
        treffer = s.execute(
            select(FixtureProfile.id)
            .join(Manufacturer, FixtureProfile.manufacturer_id == Manufacturer.id)
            .where(Manufacturer.name == hersteller, FixtureProfile.name == modell)
            .order_by(FixtureProfile.source != "builtin", FixtureProfile.id)
        ).scalars().all()
        if not treffer:
            raise SystemExit(
                f"[profil] ERROR: Profil „{geraet}“ fehlt in der Geraetebibliothek. "
                f"Erst das Geraet importieren (z. B. QLC+-Bibliothek), dann den "
                f"Generator erneut starten.")
        pid = int(treffer[0])
        if len(treffer) > 1:
            print(f"[profil] „{geraet}“ steht {len(treffer)}× in der Bibliothek — "
                  f"nehme Profil {pid} (builtin vor Import, dann kleinste ID)")
        if modus is None:
            return pid
        modi = {m.name: m for m in s.execute(
            select(FixtureMode).where(FixtureMode.fixture_id == pid)).scalars()}
        if modus not in modi:
            vorhanden = ", ".join(f"„{n}“" for n in sorted(modi)) or "keine"
            raise SystemExit(
                f"[profil] ERROR: Profil „{geraet}“ (ID {pid}) hat keinen Modus "
                f"„{modus}“ — vorhanden: {vorhanden}.")
        if kanaele is not None and modi[modus].channel_count != kanaele:
            raise SystemExit(
                f"[profil] ERROR: Modus „{modus}“ von „{geraet}“ (ID {pid}) hat "
                f"{modi[modus].channel_count} Kanaele, erwartet {kanaele}.")
    return pid
