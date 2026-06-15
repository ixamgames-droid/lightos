"""U King ZQ02001 (Mini-Gobo Moving Head) zur Fixture-Library hinzufuegen
bzw. ein veraltetes Profil korrigieren.

Seit 2026-06-09 ist das ZQ02001 fester Bestandteil des Seeds
(``fixture_db._zq02001_modes_data``) und ``ensure_builtins()`` aktualisiert
veraltete Profile automatisch in-place (z. B. die fruehere Version mit
vertauschtem Dimmer/Strobe und falschem 9-Kanal-Layout). Dieses Skript ist
nur noch ein manueller Anstoss dafuer — die Profil-Definition lebt zentral
in ``src/core/database/fixture_db.py``.

Kanal-Layout + Wertebereiche: reale Geraetedaten, siehe docs/MOVING_HEADS.md.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.core.database.fixture_db import engine, ensure_builtins
from src.core.database.models import FixtureProfile, FixtureMode


def main():
    ensure_builtins()   # legt ZQ02001 an bzw. korrigiert ein veraltetes Profil
    with Session(engine()) as s:
        prof = s.execute(
            select(FixtureProfile).where(FixtureProfile.short_name == "ZQ02001")
        ).scalars().first()
        if prof is None:
            print("FEHLER: ZQ02001 konnte nicht angelegt werden.")
            return
        modes = s.execute(
            select(FixtureMode).where(FixtureMode.fixture_id == prof.id)
        ).scalars().all()
        print(f"ZQ02001 vorhanden (Profil-ID {prof.id}):")
        for m in modes:
            print(f"  - {m.name} ({m.channel_count} Kanaele)")
        print("Layout-Details: docs/MOVING_HEADS.md")


if __name__ == "__main__":
    main()
