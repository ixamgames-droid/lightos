"""Eine Modell-Spalte ohne ALTER TABLE macht JEDE bestehende Show-DB unladbar.

Gefunden am 2026-08-02 an Davids echter ``data/current_show.db`` (30 Geraete,
8 Gruppen): ``PatchedFixture.pixel_order`` kam mit FM-13 ([PR #514]) ins Modell,
aber nicht in ``migrate_show_db``. ``create_all`` legt fehlende TABELLEN an,
niemals fehlende SPALTEN — also blieb die alte Datei ohne die Spalte, und
``AppState._reload_patch_cache`` fragt beim Start ALLE Modell-Spalten ab:

    sqlalchemy.exc.OperationalError: no such column: patched_fixtures.pixel_order

Das wirft in ``open_show`` und wird nirgends gefangen. Der Patch war damit nicht
etwa leer, sondern gar nicht erreichbar — bei einer Datei, die der Nutzer nicht
neu anlegen kann, ohne seine Show zu verlieren.

Die Falle ist bekannt (Second Brain ``reference_lightos_review_checklist``,
Klasse 3: „ein neues PatchedFixture-Feld braucht VIER Nachzieh-Stellen") und
wurde trotzdem gestellt — deshalb hier ein Gate statt einer weiteren Notiz.

Zwei Tests, bewusst verschieden:

* **strukturell** — was der Migrationspfad aus einer Alt-DB macht, muss dem
  Modell entsprechen. Faengt eine neue Spalte ohne Migration automatisch,
  weil sie im ``_URSCHEMA`` unten fehlt.
* **funktional** — eine Alt-DB MIT Daten muss nach der Migration wirklich per
  ORM ladbar sein. Eine vorhandene Spalte beweist noch nicht, dass die Zeile
  ueberlebt.
"""
from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sqlite3                                                       # noqa: E402
from sqlalchemy import create_engine, select, text                   # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from src.core.database.models import (Base, FixtureGroup,            # noqa: E402
                                      PatchedFixture, QuarantinedFixture,
                                      migrate_show_db)

# Das Schema, wie es VOR der ersten Light-Migration aussah. Alles, was danach
# dazukam, MUSS ``migrate_show_db`` selbst nachziehen — genau das misst der
# strukturelle Test. Diese Liste ist absichtlich handgepflegt und eingefroren:
# wer hier eine frisch hinzugefuegte Spalte eintraegt, statt die Migration zu
# ergaenzen, macht Alt-Shows unladbar (und muss sich das bewusst antun).
_URSCHEMA: dict[str, set[str]] = {
    "patched_fixtures": {
        "id", "fid", "label", "fixture_profile_id", "mode_name", "universe",
        "address", "channel_count", "invert_pan", "invert_tilt",
        "swap_pan_tilt", "dimmer_curve", "manufacturer_name", "fixture_name",
        "fixture_type",
    },
    "fixture_groups": {"id", "name", "cols", "rows", "positions_json"},
    # Kam als GANZE Tabelle spaeter dazu — die legt ``create_all`` einer Alt-DB
    # von selbst an, eine Migration braucht es dafuer nicht. Sobald sie aber
    # einmal existiert, gilt fuer jede weitere Spalte dieselbe Regel wie oben,
    # und genau das haelt der Eintrag hier fest.
    "quarantined_fixtures": {"id", "fid", "label", "universe", "address",
                             "grund", "verschoben_am", "daten_json"},
}

# Genau die Modelle, die auf der SHOW-Engine abgefragt werden (``AppState._session``
# bzw. ``patch_dedup`` ueber ``_show_engine``). ``Fixture``/``ChannelRange`` legt
# ``create_all`` dort zwar mit an — abgefragt werden sie aber nur auf der
# Fixture-DB, ihre Spalten-Luecken in einer Alt-Show-DB sind daher folgenlos.
_MODELLE = {"patched_fixtures": PatchedFixture, "fixture_groups": FixtureGroup,
            "quarantined_fixtures": QuarantinedFixture}

# Werte fuer alle NOT-NULL-Spalten des Urschemas. Muss handgeschrieben sein: die
# Zeile entsteht per rohem SQL, BEVOR die Migration laeuft — der ORM-Weg geht
# hier nicht, weil das Modell Spalten kennt, die die Alt-DB noch nicht hat.
_ALTE_ZEILE = {
    "fid": 7, "label": "Alt-Geraet", "fixture_profile_id": 1,
    "mode_name": "9-Kanal", "universe": 1, "address": 33, "channel_count": 9,
    "invert_pan": 0, "invert_tilt": 0, "swap_pan_tilt": 0,
    "dimmer_curve": "linear", "manufacturer_name": "Alt-Hersteller",
    "fixture_name": "Alt-Modell", "fixture_type": "par",
}


def _alte_zeile_einfuegen(conn, **abweichend) -> None:
    werte = dict(_ALTE_ZEILE, **abweichend)
    spalten = ", ".join(werte)
    platzhalter = ", ".join(f":{k}" for k in werte)
    conn.execute(text(
        f"INSERT INTO patched_fixtures ({spalten}) VALUES ({platzhalter})"), werte)


def _alt_db(path: str) -> None:
    """Legt eine Show-DB im Urschema an — echte Spaltentypen, echte Tabellen.

    Weg ueber ``create_all`` + ``DROP COLUMN`` statt handgeschriebenem DDL: so
    haben die Bestandsspalten garantiert dieselben Typen/Defaults wie im
    laufenden Betrieb, und der Test veraltet nicht, wenn sich an ihnen etwas
    aendert. ``ALTER TABLE ... DROP COLUMN`` gibt es ab SQLite 3.35 (2021).
    """
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        for tabelle, urspalten in _URSCHEMA.items():
            ist = {r[1] for r in conn.execute(text(f"PRAGMA table_info({tabelle})"))}
            for spalte in sorted(ist - urspalten):
                conn.execute(text(f"ALTER TABLE {tabelle} DROP COLUMN {spalte}"))
    eng.dispose()


class ShowDbMigrationCoverageTest(unittest.TestCase):

    def setUp(self):
        if sqlite3.sqlite_version_info < (3, 35):
            self.skipTest("ALTER TABLE DROP COLUMN braucht SQLite >= 3.35")
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db)                 # SQLite legt sie selbst an
        self.addCleanup(lambda: os.path.exists(self.db) and os.unlink(self.db))

    def _migriert(self):
        eng = create_engine(f"sqlite:///{self.db}")
        migrate_show_db(eng)
        return eng

    # ── strukturell ──────────────────────────────────────────────────────────

    def test_migration_holt_jede_modell_spalte_nach(self):
        """Nach der Migration muss eine Alt-DB dem Modell entsprechen.

        Faengt den Fall „neue Spalte ins Modell, ALTER TABLE vergessen": die
        Spalte steht dann in keiner der beiden Quellen (weder Urschema noch
        Migration) und fehlt hier.
        """
        _alt_db(self.db)
        eng = self._migriert()
        self.addCleanup(eng.dispose)
        with eng.connect() as conn:
            for tabelle, modell in _MODELLE.items():
                ist = {r[1] for r in conn.execute(
                    text(f"PRAGMA table_info({tabelle})"))}
                soll = {c.name for c in modell.__table__.columns}
                self.assertEqual(
                    soll - ist, set(),
                    f"{tabelle}: diese Modell-Spalten fehlen einer Alt-DB nach "
                    f"der Migration. Ergaenze sie in migrate_show_db "
                    f"(additives ALTER TABLE mit Default) — sonst ist JEDE "
                    f"bestehende Show-DB nicht mehr ladbar.")

    def test_urschema_bleibt_eingefroren(self):
        """Gegenprobe zum Test darueber: er waere trivial gruen, wenn jemand die
        neue Spalte einfach ins ``_URSCHEMA`` schriebe. Deshalb muss das
        Urschema eine echte TEILmenge des Modells bleiben und darf keine Spalte
        nennen, die es im Modell gar nicht (mehr) gibt."""
        for tabelle, modell in _MODELLE.items():
            soll = {c.name for c in modell.__table__.columns}
            self.assertEqual(
                _URSCHEMA[tabelle] - soll, set(),
                f"{tabelle}: _URSCHEMA nennt Spalten, die das Modell nicht hat")

    # ── funktional ───────────────────────────────────────────────────────────

    def test_alt_db_mit_daten_ist_nach_der_migration_ladbar(self):
        """Der eigentliche Schadensfall: eine Alt-DB mit Geraeten darin.

        Genau hier starb der Start — ``_reload_patch_cache`` fragt alle
        Modell-Spalten ab. Der Test prueft deshalb den ORM-Weg, nicht nur
        ``PRAGMA table_info``.
        """
        _alt_db(self.db)
        eng = create_engine(f"sqlite:///{self.db}")
        with eng.begin() as conn:
            _alte_zeile_einfuegen(conn)
            conn.execute(text(
                "INSERT INTO fixture_groups (name, cols, rows, positions_json) "
                "VALUES ('Alt-Gruppe', 2, 2, '[]')"))
        eng.dispose()

        eng = self._migriert()
        self.addCleanup(eng.dispose)
        with Session(eng) as s:
            fixtures = s.execute(select(PatchedFixture)).scalars().all()
            gruppen = s.execute(select(FixtureGroup)).scalars().all()
            self.assertEqual([f.fid for f in fixtures], [7],
                             "das Alt-Geraet muss die Migration ueberleben")
            self.assertEqual(fixtures[0].label, "Alt-Geraet")
            self.assertEqual([g.name for g in gruppen], ["Alt-Gruppe"])

    def test_neue_spalten_bekommen_bestandsverhalten_als_default(self):
        """Eine nachgezogene Spalte muss das ALTE Verhalten bedeuten.

        ``pixel_order='rowwise'`` ist der Bestand (FM-13); ein Default
        ``serpentine`` haette jede Alt-Show im 3D umsortiert, ohne dass jemand
        etwas umgestellt hat. Gleiches Muster fuer ``head_mode='auto'``.
        """
        _alt_db(self.db)
        eng = create_engine(f"sqlite:///{self.db}")
        with eng.begin() as conn:
            _alte_zeile_einfuegen(conn, fid=1, label="Alt")
        eng.dispose()

        eng = self._migriert()
        self.addCleanup(eng.dispose)
        with Session(eng) as s:
            fx = s.execute(select(PatchedFixture)).scalars().first()
            self.assertEqual(fx.pixel_order, "rowwise")
            self.assertEqual(fx.head_mode, "auto")
            self.assertEqual(fx.protocol, "dmx")

    def test_migration_ist_idempotent(self):
        """Sie laeuft bei JEDEM ``open_show`` — ein zweiter Lauf darf nicht
        werfen (ein doppeltes ADD COLUMN waere ein Fehler, den der
        Sammel-``except`` verschluckt und der die restlichen Spalten der
        gleichen Transaktion mitnaehme)."""
        _alt_db(self.db)
        eng = self._migriert()
        eng.dispose()
        eng = self._migriert()
        self.addCleanup(eng.dispose)
        with eng.connect() as conn:
            ist = {r[1] for r in conn.execute(
                text("PRAGMA table_info(patched_fixtures)"))}
        self.assertIn("pixel_order", ist)


if __name__ == "__main__":
    unittest.main()
