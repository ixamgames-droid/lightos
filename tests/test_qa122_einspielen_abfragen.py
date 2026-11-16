"""QA-122: ``bibliothek_format.einspielen`` darf je Profil nicht nachladen (N+1).

Gemessen (16.11.2026, volle eingebaute Bibliothek, 244 LightOS-Profile, ein
Einspielen ohne Stempel): rund 9700 SELECTs, davon ~7500 einzelne Lazy-Loads
``channel_ranges WHERE channel_id = ?`` — je KANAL eines frisch zur Probe
angelegten Profils eine Abfrage in ``_vergleichsform``. Das kostete ~30 s je
Lauf und liess ``tests/test_viz50a_panel_geometrie.py`` im vollen Gate unter
Last ins Zeitlimit laufen; dieselbe Arbeit macht der App-Start, sobald sich
eine Bibliotheksdatei aendert.

Nachweis ohne Wanduhr: die SQL-Anweisungen werden ueber einen
SQLAlchemy-Event-Listener gezaehlt.
"""
from __future__ import annotations

import collections
import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import event, update                           # noqa: E402
from sqlalchemy.orm import Session                             # noqa: E402

from _fixture_quelle import frische_library                    # noqa: E402

#: Feste Obergrenze SELECTs je abgeglichenem Profil. Ein Abgleich braucht eine
#: Handvoll gebuendelter Abfragen (Hersteller, Namen, Eager-Load
#: Profil/Modi/Kanaele/Bereiche); was darueber liegt, waechst mit der Zahl der
#: Kanaele — genau das N+1, das hier nicht zurueckkommen darf (vorher ~40).
SELECTS_JE_PROFIL = 12


class EinspielenAbfragenTest(unittest.TestCase):
    """Eine Bibliothek fuer die Klasse; jeder Test rollt seine Session zurueck."""

    @classmethod
    def setUpClass(cls):
        cls._eng = frische_library(cls)
        from src.core.database.fixture_db import ensure_builtins
        with contextlib.redirect_stdout(io.StringIO()):
            ensure_builtins()

    def _zaehle(self, vorbereiten=None):
        """``einspielen`` ohne Stempel (= jede Datei wird abgeglichen) in einer
        Session, die danach zurueckgerollt wird. Liefert Zaehler + Bericht."""
        from src.core.database import bibliothek_format as BF
        zaehler = collections.Counter()

        def mitzaehlen(conn, cursor, stmt, params, ctx, many):
            kopf = stmt.lstrip().split(None, 1)[0].upper()
            zaehler[kopf] += 1
            if kopf == "SELECT" and "WHERE ? = " in stmt:
                zaehler["lazy"] += 1          # klassischer Lazy-Load je Objekt

        with Session(self._eng) as s:
            if vorbereiten:
                vorbereiten(s)
                s.flush()
            event.listen(self._eng, "before_cursor_execute", mitzaehlen)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    BF.einspielen(s)
            finally:
                event.remove(self._eng, "before_cursor_execute", mitzaehlen)
            bericht = {k: list(v) if isinstance(v, list) else v
                       for k, v in BF.LETZTES_EINSPIELEN.items()}
            s.rollback()
        return zaehler, bericht

    @staticmethod
    def _profile(bericht):
        return len(bericht["stempel"]) + len(bericht["verdeckt"])

    def test_kein_lazy_load_je_kanal(self):
        zaehler, bericht = self._zaehle()
        self.assertFalse(bericht["fehler"], bericht["fehler"])
        self.assertGreater(self._profile(bericht), 50, "Vorbedingung: volle Bibliothek")
        self.assertEqual(zaehler["lazy"], 0,
                         f"{zaehler['lazy']} Einzel-Nachladungen in einspielen()")

    def test_selects_wachsen_nicht_mit_den_kanaelen(self):
        zaehler, bericht = self._zaehle()
        n = self._profile(bericht)
        self.assertLessEqual(
            zaehler["SELECT"], SELECTS_JE_PROFIL * n,
            f"{zaehler['SELECT']} SELECTs fuer {n} Profile "
            f"(Deckel {SELECTS_JE_PROFIL} je Profil)")

    def test_auch_beim_aktualisieren_kein_lazy_load(self):
        """Der teure Fall aus test_viz50a: die Formen fehlen, ``einspielen``
        baut jedes betroffene Profil neu auf."""
        from src.core.database.models import FixtureMode

        def formen_weg(s):
            s.execute(update(FixtureMode).values(grid_rows=0, grid_cols=0))

        zaehler, bericht = self._zaehle(formen_weg)
        self.assertTrue(bericht["aktualisiert"], "Vorbedingung: es gibt Arbeit")
        self.assertEqual(zaehler["lazy"], 0,
                         f"{zaehler['lazy']} Einzel-Nachladungen beim Aktualisieren")
        self.assertLessEqual(zaehler["SELECT"],
                             SELECTS_JE_PROFIL * self._profile(bericht))

    def test_soll_im_speicher_gleicht_dem_gespeicherten_profil(self):
        """Der Abgleich baut das Soll nur noch im Speicher (``_soll_profil``)
        statt es zur Probe in die DB zu schreiben. Dann muss fuer JEDE Datei
        dessen Vergleichsform genau die des eingespielten, aus der DB frisch
        geladenen Profils sein — sonst meldete jeder Start „aktualisiert“
        (oder eine echte Aenderung bliebe unbemerkt)."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from src.core.database import bibliothek_format as BF
        from src.core.database.fixture_db import profil_schluessel
        from src.core.database.models import (FixtureChannel, FixtureMode,
                                              FixtureProfile)
        with Session(self._eng) as s:
            gespeichert = {
                profil_schluessel(p.manufacturer.name, p.name): p
                for p in s.execute(
                    select(FixtureProfile)
                    .options(selectinload(FixtureProfile.manufacturer),
                             selectinload(FixtureProfile.modes)
                             .selectinload(FixtureMode.channels)
                             .selectinload(FixtureChannel.ranges))
                    .where(FixtureProfile.source == BF.SOURCE_LIGHTOS)).scalars()}
            self.assertGreater(len(gespeichert), 50, "Vorbedingung")
            verglichen = 0
            for pfad in BF.bibliothek_dateien():
                daten = BF.lade_datei(pfad)
                p = gespeichert.get(profil_schluessel(daten["hersteller"].strip(),
                                                      daten["modell"].strip()))
                if p is None:
                    continue                    # verdeckt
                with self.subTest(datei=os.path.basename(pfad)):
                    self.assertEqual(BF._vergleichsform(BF._soll_profil(daten)),
                                     BF._vergleichsform(p))
                verglichen += 1
            self.assertEqual(verglichen, len(gespeichert))
            self.assertFalse(s.new or s.dirty, "das Soll ist in die Session geraten")


if __name__ == "__main__":
    unittest.main()
