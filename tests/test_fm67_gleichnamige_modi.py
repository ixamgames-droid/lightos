"""FM-67: ``_resolve_mode`` bei gleichnamigen Modi.

Tragen zwei Modi eines Profils denselben Namen (der Fixture-Editor liess das
speichern, s. UI-74), nahm die Aufloesung stumm den aeltesten. Ein Geraet,
das im 6-Kanal-Modus gepatcht ist, fuhr dann die Kanaele des gleichnamigen
4-Kanal-Modus. Jetzt entscheidet die gespeicherte Kanalzahl mit; passt
keiner, bleibt es beim ersten (nach ID).

Alle DBs sind Temp-DBs — die echte fixtures.db bleibt unberuehrt.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace

from sqlalchemy.orm import Session

from src.core import app_state
from src.core.database.fixture_db import get_engine
from src.core.database.models import (FixtureChannel, FixtureMode, FixtureProfile,
                                      Manufacturer, create_all_idempotent)


class GleichnamigeModiTest(unittest.TestCase):

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        with Session(self.engine) as s:
            p = FixtureProfile(manufacturer=Manufacturer(name="Testwerk", short_name="TW"),
                               name="Doppel", short_name="DOPPEL", fixture_type="par",
                               source="user")
            # Reihenfolge = ID-Reihenfolge: der aeltere „A“ hat 4 Kanaele.
            for name, n in (("A", 4), ("A", 6), ("B", 8)):
                m = FixtureMode(fixture=p, name=name, channel_count=n)
                for i in range(1, n + 1):
                    m.channels.append(FixtureChannel(channel_number=i, name=f"K{i}",
                                                     attribute="intensity"))
            s.add(p)
            s.commit()
            self.pid = p.id

    def _modus(self, mode_name, channel_count):
        f = SimpleNamespace(fixture_profile_id=self.pid, mode_name=mode_name,
                            channel_count=channel_count)
        with Session(self.engine) as s:
            m = app_state._resolve_mode(s, f)
            return None if m is None else (m.name, m.channel_count)

    def test_gespeicherte_kanalzahl_waehlt_den_gleichnamigen_modus(self):
        # Vor FM-67: ("A", 4) — der aeltere gleichnamige Modus gewann.
        self.assertEqual(self._modus("A", 6), ("A", 6))

    def test_aelterer_gleichnamiger_modus_bei_passender_kanalzahl(self):
        self.assertEqual(self._modus("A", 4), ("A", 4))

    def test_keine_kanalzahl_passt_erster_gleichnamiger_bleibt(self):
        self.assertEqual(self._modus("A", 10), ("A", 4))
        self.assertEqual(self._modus("A", None), ("A", 4))

    def test_name_schlaegt_weiter_die_kanalzahl(self):
        # Kanalzahl 8 gehoert zu „B“ — der exakte Name „A“ bleibt Stufe 1.
        self.assertEqual(self._modus("A", 8), ("A", 4))

    def test_rueckfall_ueber_kanalzahl_unveraendert(self):
        self.assertEqual(self._modus("weg", 6), ("A", 6))
        self.assertEqual(self._modus("weg", 99), ("A", 4))


if __name__ == "__main__":
    unittest.main()
