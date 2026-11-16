"""QA-121 (Fund 2): LAS-28-Marker nur bei gesicherter Umsetzung.

Scheitert beim Laden einer Alt-Show (ohne Marker) die SH-LASER3W-Erkennung
(Geraete-DB wirft), laeuft die Flip-Umsetzung nicht. Das naechste Speichern
schrieb trotzdem ``attribut_migrationen: ["LAS-28"]`` — danach wurde die
Umsetzung nie mehr versucht und ``laser_twist#2/#3`` blieben wirkungslos.
Jetzt: kein Marker, solange die Umsetzung nicht gesichert lief; das naechste
normale Laden setzt die Schluessel um.
"""
import json
import os
import sys
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state
from src.core.database import fixture_db as FDB
from src.core.show.show_file import _show_daten, reset_show

import test_cdx65_sh_laser3w_flip_migration as cdx65

ALT, NEU = cdx65.ALT, cdx65.NEU
_ERKENNUNG = {"_sh_laser3w_fids", "_sh_laser3w_befund"}


class Las28MarkerGesichert(cdx65.ShLaser3wFlipMigration):
    """Erbt Bibliothek/Patch-Aufbau von CDX-65; dessen Tests laufen dort."""

    def _erkennung_wirft(self):
        echt = FDB.engine

        def engine(*a, **k):
            if sys._getframe(1).f_code.co_name in _ERKENNUNG:
                raise RuntimeError("Geraete-DB voruebergehend weg (Test)")
            return echt(*a, **k)
        FDB.engine = engine
        self.addCleanup(setattr, FDB, "engine", echt)
        return echt

    def test_fehlgeschlagene_erkennung_schreibt_keinen_marker(self):
        echt = self._erkennung_wirft()
        cdx65._laden(self._alte_show())
        st = get_state()
        self.assertEqual(st.programmer[1], ALT, "Testannahme: nichts umgesetzt")
        daten = _show_daten(st, [])
        self.assertNotIn("LAS-28", daten.get("attribut_migrationen") or [])

        # Gespeicherten Stand normal neu laden: jetzt wird umgesetzt.
        FDB.engine = echt
        daten = json.loads(json.dumps(daten))
        cdx65._laden(daten)
        self.assertEqual(get_state().programmer[1], NEU)
        self.assertIn("LAS-28", _show_daten(get_state(), [])["attribut_migrationen"])

    def test_neue_show_nach_fehlschlag_bekommt_marker(self):
        self._erkennung_wirft()
        cdx65._laden(self._alte_show())
        reset_show()
        self.assertIn("LAS-28", _show_daten(get_state(), [])["attribut_migrationen"])

    def test_show_mit_marker_behaelt_ihn_auch_bei_fehler(self):
        self._erkennung_wirft()
        cdx65._laden(self._alte_show(attribut_migrationen=["LAS-28"]))
        self.assertIn("LAS-28", _show_daten(get_state(), [])["attribut_migrationen"])


# Die geerbten CDX-65-Tests nicht doppelt laufen lassen.
for _n in [n for n in dir(cdx65.ShLaser3wFlipMigration) if n.startswith("test_")]:
    setattr(Las28MarkerGesichert, _n, None)

if __name__ == "__main__":
    unittest.main()
