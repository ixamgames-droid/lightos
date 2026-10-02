"""QA-68: ``tools/library_testreste.py`` meldet Dubletten eines Builtin-Profils.

Auf dem Windows-Rechner lag der ZQ06121 zweimal in der Bibliothek, beide beim
Hersteller „U King", beide ``source='builtin'`` — ein Rest aus Testlaeufen, die
vor QA-54/QA-58 in die echte Bibliothek schrieben. Vier Tests rissen an
``MultipleResultsFound``. Das Werkzeug fand damals nur benannte Testreste
(``TEST-DualTilt``), die Dublette trug keinen Test-Praefix.

Regel: ein Modellkuerzel steht je Hersteller hoechstens einmal als Builtin.
Gleiches Kuerzel bei VERSCHIEDENEN Herstellern ist erlaubt (Martin/Showtec
„Acrobat"), ebenso eine Nutzer- oder QLC+-Kopie neben dem Builtin.
"""
import contextlib
import io
import os
import sys
import unittest

from sqlalchemy import select
from sqlalchemy.orm import Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import library_testreste as LT                                    # noqa: E402
from _fixture_quelle import frische_library                       # noqa: E402
from src.core.database import fixture_db as FDB                   # noqa: E402
from src.core.database.models import FixtureProfile, Manufacturer  # noqa: E402

KUERZEL = "ZQ06121"


class _Basis(unittest.TestCase):

    def setUp(self):
        self.motor = frische_library(self)
        with Session(self.motor) as s:
            echt = s.scalars(select(FixtureProfile).where(
                FixtureProfile.short_name == KUERZEL,
                FixtureProfile.source == "builtin")).one()
            self.echt_id = echt.id
            self.hersteller_id = echt.manufacturer_id
            self.hersteller = echt.manufacturer.name

    def _profil(self, *, kuerzel=KUERZEL, hersteller_id=None, source="builtin"):
        """Ein Profil OHNE Modi — so sah der Rest aus (ohne Geometrie)."""
        with Session(self.motor) as s:
            p = FixtureProfile(manufacturer_id=hersteller_id or self.hersteller_id,
                               name=f"{kuerzel} (Rest)", short_name=kuerzel,
                               source=source)
            s.add(p)
            s.commit()
            return p.id

    def _hersteller(self, name):
        with Session(self.motor) as s:
            m = Manufacturer(name=name)
            s.add(m)
            s.commit()
            return m.id


class FrischeBibliothek(_Basis):

    def test_keine_dubletten_auch_nach_dem_backfill(self):
        """Der Code legt jedes Builtin genau einmal an — auch ``ensure_builtins``
        zweimal hintereinander auf einer befuellten Bibliothek."""
        FDB.ensure_builtins()
        FDB.ensure_builtins()
        self.assertEqual(LT.builtin_dubletten(self.motor), [])


class DubletteWirdGemeldet(_Basis):

    def test_zweiter_zq06121_beim_selben_hersteller(self):
        rest = self._profil()
        gruppen = LT.builtin_dubletten(self.motor)
        self.assertEqual([(h, k, [e[0] for e in ee]) for h, k, ee in gruppen],
                         [(self.hersteller, KUERZEL, [self.echt_id, rest])])
        echt, kopie = gruppen[0][2]
        self.assertGreater(echt[2], 0, "das echte Profil hat Modi")
        self.assertTrue(echt[3], "der ZQ06121 traegt ein Raster")
        self.assertEqual(kopie[1:], (f"{KUERZEL} (Rest)", 0, False))

    def test_schreibweise_des_kuerzels_zaehlt_nicht(self):
        self._profil(kuerzel=" zq06121 ")
        gruppen = LT.builtin_dubletten(self.motor)
        self.assertEqual(len(gruppen), 1)
        self.assertEqual(len(gruppen[0][2]), 2)


class KeineDublette(_Basis):
    """Positivkontrolle: was erlaubt ist, bleibt still."""

    def test_gleiches_kuerzel_anderer_hersteller(self):
        self._profil(hersteller_id=self._hersteller("Anderer Hersteller QA68"))
        self.assertEqual(LT.builtin_dubletten(self.motor), [])

    def test_kopie_mit_anderer_quelle(self):
        for quelle in ("user", "qlcplus"):
            with self.subTest(quelle=quelle):
                self._profil(source=quelle)
        self.assertEqual(LT.builtin_dubletten(self.motor), [])


class Kommandozeile(_Basis):

    def _main(self, *argv):
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            rc = LT.main(list(argv))
        return rc, puffer.getvalue()

    def test_meldet_und_entfernt_nicht(self):
        rest = self._profil()
        rc, text = self._main("--entfernen")
        self.assertEqual(rc, 0)
        self.assertIn("QA-68", text)
        self.assertIn(f"id={self.echt_id}", text)
        self.assertIn(f"id={rest}", text)
        with Session(self.motor) as s:
            self.assertIsNotNone(s.get(FixtureProfile, self.echt_id))
            self.assertIsNotNone(s.get(FixtureProfile, rest),
                                 "eine Dublette darf das Werkzeug nie loeschen")

    def test_ohne_dublette_kein_abschnitt(self):
        rc, text = self._main()
        self.assertEqual(rc, 0)
        self.assertNotIn("QA-68", text)
        self.assertIn("Keine Test-Rueckstaende gefunden.", text)


if __name__ == "__main__":
    unittest.main()
