"""FLD-01b: Fixture-Gruppen bekommen einen (verschachtelten) Ordnerpfad.

Schwerpunkt: die idempotente DB-Migration (ALTER TABLE) ergänzt die folder-Spalte
in bestehenden Show-DBs, ohne Daten zu verlieren.

Hinweis: Engines werden in finally per dispose() geschlossen, sonst kann
TemporaryDirectory die SQLite-Datei auf Windows nicht löschen (Datei noch offen).
"""
import os
import tempfile
import unittest

from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import Session

from src.core.database.models import FixtureGroup, migrate_show_db, create_db


def _cols(engine) -> set:
    with engine.begin() as c:
        return {r[1] for r in c.execute(text("PRAGMA table_info(fixture_groups)"))}


class MigrationTest(unittest.TestCase):
    def test_alter_adds_folder_to_old_db(self):
        with tempfile.TemporaryDirectory() as td:
            eng = create_engine(f"sqlite:///{os.path.join(td, 'old.db')}")
            try:
                with eng.begin() as c:    # ALTE Tabelle ohne folder-Spalte
                    c.execute(text("CREATE TABLE fixture_groups "
                                   "(id INTEGER PRIMARY KEY, name VARCHAR, cols INTEGER, "
                                   "rows INTEGER, positions_json TEXT)"))
                    c.execute(text("INSERT INTO fixture_groups (name, cols, rows, positions_json) "
                                   "VALUES ('Alt', 8, 8, '{}')"))
                self.assertNotIn("folder", _cols(eng))
                migrate_show_db(eng)
                self.assertIn("folder", _cols(eng))
                with Session(eng) as s:
                    old = s.execute(select(FixtureGroup)).scalars().first()
                    self.assertEqual(old.folder, "")          # Default für Alt-Zeile
                    s.add(FixtureGroup(name="Neu", folder="Front/Wash", positions_json="{}"))
                    s.commit()
                with Session(eng) as s:
                    got = s.execute(select(FixtureGroup).where(FixtureGroup.name == "Neu")).scalars().one()
                    self.assertEqual(got.folder, "Front/Wash")
            finally:
                eng.dispose()

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            eng = create_db(os.path.join(td, "x.db"))
            try:
                migrate_show_db(eng)        # erneut -> No-Op
                migrate_show_db(eng)
                self.assertIn("folder", _cols(eng))
            finally:
                eng.dispose()

    def test_create_db_has_folder(self):
        with tempfile.TemporaryDirectory() as td:
            eng = create_db(os.path.join(td, "n.db"))
            try:
                self.assertIn("folder", _cols(eng))
            finally:
                eng.dispose()


class ModelDefaultTest(unittest.TestCase):
    def test_default_folder_empty(self):
        with tempfile.TemporaryDirectory() as td:
            eng = create_db(os.path.join(td, "m.db"))
            try:
                with Session(eng) as s:
                    s.add(FixtureGroup(name="Y", positions_json="{}"))
                    s.commit()
                    got = s.execute(select(FixtureGroup)).scalars().one()
                    self.assertEqual(got.folder, "")
            finally:
                eng.dispose()


if __name__ == "__main__":
    unittest.main()
