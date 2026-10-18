"""FM-65 — Show laden: der gespeicherte Modus wird VOR der Profil-ID geprueft.

Herkunft Codex-Review #935: ``show_file._resolve_fixture_profile_id`` nahm im
Schnellweg „ID passt und Name (und Hersteller) gleich“ die ID sofort an — ohne
Modus und Kanalzahl anzusehen. Profil-IDs sind SQLite-Auto-IDs und kollidieren
ueber Geraete-DBs: eine Show von Rechner X (DB A) zeigt mit ihrer ID hier (DB B)
womoeglich auf ein GLEICHNAMIGES Profil mit anderen Modi. Dann fuhr still die
falsche Kanalbelegung.

Jetzt: passt der Modus der Show (Name und/oder Kanalzahl, soweit gespeichert)
im Profil der ID nicht, laeuft der normale Abgleich (FM-63-Stufen); bleibt es
mangels besseren Profils bei der ID, steht eine Meldung in ``_ladeprobleme``.
Legacy-Shows ohne Modus/Kanalzahl verhalten sich wie bisher.

Beide Geraete-DBs sind Wegwerf-DBs im Temp-Bereich.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                      # noqa: E402
from sqlalchemy.orm import Session                                 # noqa: E402

from src.core.database import fixture_db as FDB                   # noqa: E402
from src.core.database.models import (FixtureChannel, FixtureMode,  # noqa: E402
                                      FixtureProfile, Manufacturer)

ID = 4711
HERSTELLER = "Testwerk"
MODELL = "Spot 65"


class _Basis(unittest.TestCase):

    def setUp(self):
        self.verz = tempfile.mkdtemp(prefix="lightos_fm65_")
        self.addCleanup(shutil.rmtree, self.verz, True)
        alt = FDB._engine
        self.db_a = FDB.get_engine(os.path.join(self.verz, "a", "fixtures.db"))
        self.db_b = FDB.get_engine(os.path.join(self.verz, "b", "fixtures.db"))

        def zurueck():
            FDB._engine = alt
            self.db_a.dispose()
            self.db_b.dispose()
        self.addCleanup(zurueck)

        from src.core.show import show_file as SF
        self.SF = SF
        SF._ladeprobleme.clear()
        SF._ladehinweise.clear()
        self.addCleanup(SF._ladeprobleme.clear)
        self.addCleanup(SF._ladehinweise.clear)

        # Rechner X (DB A): unter ID 4711 steht „Spot 65“ mit „Basic“ 6 Kanaele.
        self._profil(self.db_a, ID, "qlcplus", (("Basic", 6),))

    @staticmethod
    def _profil(motor, pid, source, modi) -> int:
        with Session(motor) as s:
            m = s.execute(select(Manufacturer).where(
                Manufacturer.name == HERSTELLER)).scalar_one_or_none()
            if m is None:
                m = Manufacturer(name=HERSTELLER, short_name=HERSTELLER[:8])
            p = FixtureProfile(id=pid, manufacturer=m, name=MODELL,
                               short_name=f"{MODELL}-{pid}"[:40],
                               fixture_type="moving_head", source=source)
            for name, zahl in modi:
                mo = FixtureMode(fixture=p, name=name, channel_count=zahl)
                for i in range(1, zahl + 1):
                    mo.channels.append(FixtureChannel(
                        channel_number=i, name=f"K{i}", attribute="raw"))
            s.add(p)
            s.commit()
            return p.id

    def _hier(self, motor):
        FDB._engine = motor

    def _laden(self, **show):
        d = {"fid": 1, "label": "Spot", "fixture_profile_id": ID,
             "universe": 1, "address": 1, "manufacturer_name": HERSTELLER,
             "fixture_name": MODELL, "fixture_type": "moving_head"}
        d.update(show)
        return self.SF._patched_fixture_from_data(d, 1).fixture_profile_id

    @property
    def probleme(self):
        return self.SF.letzte_ladeprobleme()


class KollisionUeberZweiDBs(_Basis):
    """In DB B traegt ID 4711 ein gleichnamiges Profil mit ANDEREN Modi."""

    def setUp(self):
        super().setUp()
        self._profil(self.db_b, ID, "qlcplus", (("Extended", 12),))
        self.richtig = self._profil(self.db_b, ID + 1, "qlcplus", (("Basic", 6),))
        self._hier(self.db_b)

    def test_modus_und_kanalzahl__das_richtige_profil(self):
        self.assertEqual(self._laden(mode_name="Basic", channel_count=6),
                         self.richtig)
        self.assertEqual(self.probleme, [])

    def test_nur_kanalzahl_gespeichert__das_richtige_profil(self):
        self.assertEqual(self._laden(channel_count=6), self.richtig)

    def test_nur_modusname_gespeichert__das_richtige_profil(self):
        self.assertEqual(self._laden(mode_name="Basic"), self.richtig)

    def test_auf_rechner_x_bleibt_die_id(self):
        """Gegenstueck: in DB A passt der Modus — Schnellweg, keine Meldung."""
        self._hier(self.db_a)
        self.assertEqual(self._laden(mode_name="Basic", channel_count=6), ID)
        self.assertEqual(self.probleme, [])
        self.assertEqual(self.SF.letzte_ladehinweise(), [])


class SchnellwegUnveraendert(_Basis):

    def test_id_und_modus_passen__keine_meldung(self):
        # Auch mit einem gleichnamigen zweiten Profil: keine Dubletten-Meldung,
        # weil der Schnellweg greift.
        self._profil(self.db_a, ID + 1, "builtin", (("Basic", 6),))
        self._hier(self.db_a)
        self.assertEqual(self._laden(mode_name="Basic", channel_count=6), ID)
        self.assertEqual(self.probleme, [])
        self.assertEqual(self.SF.letzte_ladehinweise(), [])

    def test_legacy_ohne_modus_und_kanalzahl__id_bleibt_still(self):
        self._profil(self.db_b, ID, "qlcplus", (("Extended", 12),))
        self._profil(self.db_b, ID + 1, "builtin", (("Basic", 6),))
        self._hier(self.db_b)
        self.assertEqual(self._laden(), ID)
        self.assertEqual(self.probleme, [])
        self.assertEqual(self.SF.letzte_ladehinweise(), [])

    def test_zwilling_gilt_im_schnellweg_als_modus(self):
        """FM-73: „Basic (2)“ mit gleicher Kanalzahl ist der Modus der Show."""
        self._profil(self.db_b, ID, "qlcplus", (("Basic", 4), ("Basic (2)", 6)))
        self._hier(self.db_b)
        self.assertEqual(self._laden(mode_name="Basic", channel_count=6), ID)
        self.assertEqual(self.probleme, [])


class KeinBesseresProfil(_Basis):

    def setUp(self):
        super().setUp()
        self._profil(self.db_b, ID, "qlcplus", (("Extended", 12),))
        self._hier(self.db_b)

    def test_id_bleibt__aber_laut(self):
        self.assertEqual(self._laden(mode_name="Basic", channel_count=6), ID)
        self.assertTrue(any("NICHT" in p and "Basic" in p for p in self.probleme),
                        self.probleme)

    def test_nur_kanalzahl__id_bleibt__aber_laut(self):
        self.assertEqual(self._laden(channel_count=6), ID)
        self.assertTrue(any("NICHT" in p and "6 Kanaelen" in p
                            for p in self.probleme), self.probleme)

    def test_kein_besseres__id_geht_vor_anderem_gleichnamigem(self):
        """Hat auch das zweite gleichnamige Profil den Modus nicht, wird nicht
        auf dieses gewechselt (es waere nur ein anderer Fehlgriff)."""
        self._profil(self.db_b, ID + 1, "builtin", (("Wieder anders", 9),))
        self.assertEqual(self._laden(mode_name="Basic", channel_count=6), ID)
        self.assertTrue(any("NICHT" in p for p in self.probleme), self.probleme)


if __name__ == "__main__":
    unittest.main()
