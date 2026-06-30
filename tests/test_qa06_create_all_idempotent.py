"""QA-06: create_all idempotent gegen ein bereits vorhandenes Schema.

Hintergrund: ``Base.metadata.create_all(checkfirst=True)`` reflektiert vor jedem
``CREATE`` das ``sqlite_master``. Greifen zwei Verbindungen/Laeufe auf dieselbe
SQLite-Datei zu, liegt zwischen Reflexion und ``CREATE`` ein TOCTOU-Fenster — der
eigene ``CREATE`` kann dann mit ``table ... already exists`` kollidieren, obwohl
die Tabellen bereits da sind. Symptom in der Suite: ``test_vc_tempo_live_coupling``
errorte sporadisch im ``reset_show``-Teardown (``manufacturers already exists``).
``create_all_idempotent`` schluckt genau diesen harmlosen Fall und laesst jeden
anderen ``OperationalError`` weiterfliegen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError

from src.core.database.models import Base, create_all_idempotent


class CreateAllIdempotent(unittest.TestCase):
    def test_creates_tables_on_empty_db(self):
        import tempfile
        p = os.path.join(tempfile.gettempdir(), f"qa06_empty_{os.getpid()}.db")
        for sfx in ("", "-wal", "-shm"):
            try:
                os.remove(p + sfx)
            except OSError:
                pass
        eng = create_engine(f"sqlite:///{p}", echo=False)
        try:
            create_all_idempotent(eng)
            self.assertIn("manufacturers", inspect(eng).get_table_names())
        finally:
            eng.dispose()
            for sfx in ("", "-wal", "-shm"):
                try:
                    os.remove(p + sfx)
                except OSError:
                    pass

    def test_swallows_already_exists(self):
        orig = Base.metadata.create_all

        def boom(engine):
            raise OperationalError(
                "CREATE TABLE manufacturers (...)", {},
                Exception("table manufacturers already exists"))

        Base.metadata.create_all = boom
        try:
            # Darf NICHT durchschlagen — die Tabellen sind ja bereits da.
            create_all_idempotent(object())
        finally:
            Base.metadata.create_all = orig

    def test_reraises_other_operational_errors(self):
        orig = Base.metadata.create_all

        def boom(engine):
            raise OperationalError("CREATE TABLE x (...)", {},
                                   Exception("disk I/O error"))

        Base.metadata.create_all = boom
        try:
            with self.assertRaises(OperationalError):
                create_all_idempotent(object())
        finally:
            Base.metadata.create_all = orig


if __name__ == "__main__":
    unittest.main()
