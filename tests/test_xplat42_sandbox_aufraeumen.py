"""XPLAT-42 — das Bild-Werkzeug raeumt seine Sandbox auch unter Windows weg.

Befund (Sitzung B, Windows-Gate 01.10.2026): ``tools/anleitungsbilder.py``
loeschte die Sandbox mit ``rmtree(ignore_errors=True)``, solange der eigene
Prozess die SQLite-Dateien noch offen hielt. Linux loescht offene Dateien,
Windows nicht — es blieben ``current_show.db`` (+ ``-wal``/``-shm``) und
``fixtures.db`` liegen, und ``ignore_errors`` verschluckte es.

Der Ende-zu-Ende-Beweis ist ``MiniLaufTest::test_sandbox_pfade_liegen_alle_im_temp_ordner``
in ``tests/test_anleitungsbilder.py`` (unter Windows vorher rot). Hier die
zwei Bausteine einzeln, auf jeder Plattform:

* ``aufraeumen`` schliesst vorher die DB-Engines der geladenen Module und
  verwirft die Fixture-Engine (sonst haelt sie die Datei weiter offen);
* was trotzdem liegen bleibt, kommt als Liste zurueck — gemeldet statt
  verschluckt.
"""
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from anleitungsbilder import sandbox  # noqa: E402


class _Engine:
    def __init__(self):
        self.disposed = 0

    def dispose(self):
        self.disposed += 1


def _sandbox_mit_dateien():
    basis = tempfile.mkdtemp(prefix="lightos_xplat42_")
    for rel in (("arbeit", "data", "current_show.db"),
                ("xdg", "data", "LightOS", "fixtures.db")):
        p = os.path.join(basis, *rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"x")
    return sandbox.Sandbox(basis=basis)


class AufraeumenTest(unittest.TestCase):

    def test_loescht_die_sandbox_vollstaendig(self):
        sb = _sandbox_mit_dateien()
        self.assertEqual(sandbox.aufraeumen(sb), [])
        self.assertFalse(os.path.exists(sb.basis))

    def test_rest_wird_gemeldet_statt_verschluckt(self):
        # Windows-Fall nachgestellt: rmtree kann nichts loeschen.
        sb = _sandbox_mit_dateien()
        try:
            with mock.patch.object(shutil, "rmtree"), \
                    mock.patch.object(sandbox, "_datenbanken_freigeben"):
                rest = sandbox.aufraeumen(sb, versuche=2)
            namen = sorted(os.path.basename(p) for p in rest)
            self.assertEqual(namen, ["current_show.db", "fixtures.db"])
            self.assertTrue(all(p.startswith(sb.basis + os.sep) for p in rest))
        finally:
            shutil.rmtree(sb.basis, ignore_errors=True)

    def test_engines_werden_vor_dem_loeschen_geschlossen(self):
        show_eng, fix_eng = _Engine(), _Engine()
        state = types.SimpleNamespace(_show_engine=show_eng)
        app_state = types.ModuleType("src.core.app_state")
        app_state.get_state = lambda: state
        fixture_db = types.ModuleType("src.core.database.fixture_db")
        fixture_db._engine = fix_eng
        sb = _sandbox_mit_dateien()
        with mock.patch.dict(sys.modules, {"src.core.app_state": app_state,
                                           "src.core.database.fixture_db": fixture_db}):
            self.assertEqual(sandbox.aufraeumen(sb), [])
        self.assertEqual(show_eng.disposed, 1)
        self.assertEqual(fix_eng.disposed, 1)
        # Verworfen, nicht nur geleert: sonst oeffnete der naechste Zugriff
        # dieselbe Datei ueber den alten Pool neu.
        self.assertIsNone(fixture_db._engine)

    def test_importiert_nichts_neu(self):
        # Nur bereits geladene Module — das Aufraeumen darf keinen src-Import
        # ausloesen (das Werkzeug kann vor dem ersten src-Import scheitern).
        sb = _sandbox_mit_dateien()
        ohne = {k: v for k, v in sys.modules.items()
                if not k.startswith("src.core.app_state")
                and not k.startswith("src.core.database.fixture_db")}
        with mock.patch.dict(sys.modules, ohne, clear=True):
            self.assertEqual(sandbox.aufraeumen(sb), [])
            self.assertNotIn("src.core.app_state", sys.modules)
            self.assertNotIn("src.core.database.fixture_db", sys.modules)


if __name__ == "__main__":
    unittest.main()
