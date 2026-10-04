"""FM-63: Ein mitgeliefertes LightOS-Profil loest den alten QLC+-Import ab.

Entscheidung des Projektinhabers (2026-10-04): Die Profile der eigenen
Bibliothek (``fixtures/bibliothek/``, ``source='lightos'``) sollen alte
QLC+-Importe mit gleichem Hersteller + Modell ABLOESEN. Bis hierher war es
umgekehrt: ``bibliothek_format._abgleichen`` meldete die Datei als „verdeckt“,
sobald es Hersteller + Modell schon als Import gab — in einer gewachsenen
Geraetedatenbank zeigten Suche und Fixture-Browser deshalb immer den alten
Import, das verbesserte Profil kam nie in die DB.

Gewaehlte Variante: der Import bleibt unveraendert in der DB (Shows zeigen
ueber Profil-ID + Modusname auf ihn), Auswahl und Suche blenden ihn aus.

Kernaussagen:

* QLC+-Import + LightOS-Datei gleichen Namens -> das LightOS-Profil wird
  angelegt und gewinnt in Suche und Fixture-Browser; der Import fehlt dort.
* Schreibweise egal (Gross/Klein, Leerzeichen).
* Ein eigenes Profil (``source='user'``) gleichen Namens bleibt unangetastet
  und sichtbar.
* Ein bestehender Patch auf den alten Import laedt weiter — mit dessen ID und
  dessen Kanalbelegung; eine Show mit fremder ID landet ohne Dubletten-Warnung
  beim LightOS-Profil.
* Idempotent: ein zweiter Lauf aendert nichts.

Alle DBs sind Temp-DBs — die echte Bibliothek bleibt unberuehrt.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                      # noqa: E402
from sqlalchemy.orm import Session                                 # noqa: E402

from src.core.database import bibliothek_format as BF             # noqa: E402
from src.core.database import fixture_db as FDB                   # noqa: E402
from src.core.database.models import (FixtureChannel, FixtureMode,  # noqa: E402
                                      FixtureProfile, Manufacturer)


def _datei(**ueber) -> dict:
    d = {
        "format_version": 1, "hersteller": "Testwerk", "modell": "Par 7",
        "kurzname": "PAR7LOS", "typ": "par", "leistung_w": 70,
        "quelle": {"titel": "Bedienungsanleitung Par 7", "version": "1.2",
                   "datum": "2026-01-01", "url": "https://example.invalid/par7.pdf"},
        "herkunft": {"art": "hersteller-handbuch", "lizenz": "eigen"},
        "autor": "LightOS",
        "geprueft": {"ok": False, "wie": "nur Handbuch"},
        "modi": [{
            "name": "4-Kanal",
            "kanaele": [
                {"name": "Dimmer", "attribut": "intensity", "default": 0, "highlight": 255},
                {"name": "Rot", "attribut": "color_r", "default": 0, "highlight": 255},
                {"name": "Gruen", "attribut": "color_g", "default": 0, "highlight": 255},
                {"name": "Blau", "attribut": "color_b", "default": 0, "highlight": 255},
            ],
        }],
    }
    d.update(ueber)
    return d


class _Basis(unittest.TestCase):
    """Temp-Fixture-DB als ``fixture_db._engine`` + Temp-Bibliothek."""

    def setUp(self):
        self.verz = tempfile.mkdtemp(prefix="lightos_fm63_")
        self.addCleanup(shutil.rmtree, self.verz, True)
        alt = FDB._engine
        self.eng = FDB.get_engine(os.path.join(self.verz, "fixtures.db"))
        FDB._engine = self.eng

        def zurueck():
            FDB._engine = alt
            self.eng.dispose()
        self.addCleanup(zurueck)

    def _profil(self, hersteller: str, modell: str, source: str,
                modus: str = "3 Kanal", attrs=("color_r", "color_g", "color_b")) -> int:
        with Session(self.eng) as s:
            m = s.execute(select(Manufacturer).where(
                Manufacturer.name == hersteller)).scalar_one_or_none()
            if m is None:
                m = Manufacturer(name=hersteller, short_name=hersteller[:8])
            p = FixtureProfile(manufacturer=m, name=modell, short_name=modell[:40],
                               fixture_type="par", source=source)
            mo = FixtureMode(fixture=p, name=modus, channel_count=len(attrs))
            for i, a in enumerate(attrs, start=1):
                mo.channels.append(FixtureChannel(channel_number=i, name=a, attribute=a))
            s.add(p)
            s.commit()
            return p.id

    def _spielen(self, *dateien) -> None:
        wurzel = os.path.join(self.verz, "bib")
        os.makedirs(wurzel, exist_ok=True)
        for d in dateien:
            BF.schreibe(d, os.path.join(wurzel, BF.dateiname(d["hersteller"], d["modell"])))
        with Session(self.eng) as s:
            BF.einspielen(s, wurzel)
            s.commit()

    def _quellen(self, modell: str) -> list[tuple[int, str]]:
        with Session(self.eng) as s:
            return [(i, src) for i, src in s.execute(
                select(FixtureProfile.id, FixtureProfile.source)
                .where(FixtureProfile.name == modell).order_by(FixtureProfile.id))]

    def _suche(self, begriff: str) -> list[int]:
        """Profil-IDs aus ``search_fixtures`` — die Profile legt der Test selbst
        an (QA-61: kein Verlass auf die lokale Bibliothek)."""
        return [f.id for f in FDB.search_fixtures(begriff)]

    def _lightos_id(self, modell: str = "Par 7") -> int:
        ids = [i for i, src in self._quellen(modell) if src == "lightos"]
        self.assertEqual(len(ids), 1, self._quellen(modell))
        return ids[0]


class A_LightosLoestImportAb(_Basis):

    def test_lightos_profil_wird_neben_dem_import_angelegt(self):
        alt = self._profil("Testwerk", "Par 7", "qlcplus")
        self._spielen(_datei())
        self.assertEqual([src for _i, src in self._quellen("Par 7")],
                         ["qlcplus", "lightos"])
        self.assertEqual(BF.LETZTES_EINSPIELEN["verdeckt"], [])
        self.assertEqual(BF.LETZTES_EINSPIELEN["neu"], ["Testwerk / Par 7"])
        # Der Import selbst bleibt byte-gleich (Modus + Kanaele) erhalten.
        prof = FDB.get_fixture(alt)
        self.assertEqual(prof.source, "qlcplus")
        self.assertEqual([(m.name, [c.attribute for c in m.channels]) for m in prof.modes],
                         [("3 Kanal", ["color_r", "color_g", "color_b"])])

    def test_suche_zeigt_lightos_statt_import(self):
        alt = self._profil("Testwerk", "Par 7", "qlcplus")
        self._spielen(_datei())
        neu = self._lightos_id()
        for q in ("Par 7", "Testwerk", "par"):
            ids = self._suche(q)
            self.assertIn(neu, ids, q)
            self.assertNotIn(alt, ids, q)

    def test_schreibweise_egal(self):
        alt = self._profil("TESTWERK ", "par  7", "qlcplus")
        self._spielen(_datei())
        neu = self._lightos_id()
        self.assertEqual(FDB.abgeloeste_profil_ids(), {alt})
        ids = self._suche("7")
        self.assertEqual(ids, [neu])

    def test_fixture_browser_bietet_nur_lightos_an(self):
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication([])  # noqa: F841
        from src.ui.widgets.fixture_browser import FixtureBrowserDialog
        from PySide6.QtCore import Qt
        alt = self._profil("Testwerk", "Par 7", "qlcplus")
        anderes = self._profil("Testwerk", "Bar 9", "qlcplus")
        self._spielen(_datei())
        neu = self._lightos_id()

        def ids(d) -> list[int]:
            out, stack = [], [d._tree.topLevelItem(i)
                              for i in range(d._tree.topLevelItemCount())]
            while stack:
                it = stack.pop()
                v = it.data(0, Qt.ItemDataRole.UserRole)
                if v is not None:
                    out.append(int(v))
                stack.extend(it.child(j) for j in range(it.childCount()))
            return sorted(out)

        d = FixtureBrowserDialog(1)
        self.addCleanup(d.deleteLater)
        self.assertEqual(ids(d), sorted([neu, anderes]))
        d._search.setText("Par 7")
        self.assertEqual(ids(d), [neu])
        self.assertNotIn(alt, ids(d))

    def test_idempotent(self):
        self._profil("Testwerk", "Par 7", "qlcplus")
        self._spielen(_datei())
        vorher = self._quellen("Par 7")
        self._spielen(_datei())
        self.assertEqual(self._quellen("Par 7"), vorher)
        self.assertEqual(BF.LETZTES_EINSPIELEN["neu"], [])
        self.assertEqual(BF.LETZTES_EINSPIELEN["aktualisiert"], [])


class B_EigenesProfilBleibt(_Basis):

    def test_user_profil_bleibt_unangetastet_und_sichtbar(self):
        eigen = self._profil("Testwerk", "Par 7", "user", modus="Mein Modus")
        self._spielen(_datei())
        self.assertEqual(self._quellen("Par 7"), [(eigen, "user")])
        self.assertEqual(BF.LETZTES_EINSPIELEN["verdeckt"], ["Testwerk / Par 7"])
        self.assertEqual(self._suche("Par 7"), [eigen])
        self.assertEqual([m.name for m in FDB.get_fixture(eigen).modes], ["Mein Modus"])
        self.assertEqual(FDB.abgeloeste_profil_ids(), set())

    def test_user_neben_import_verdeckt_weiter(self):
        """User + Import + Datei: die Datei bleibt draussen (wie bisher), und
        der Import wird nicht ausgeblendet — es gibt ja kein LightOS-Profil."""
        imp = self._profil("Testwerk", "Par 7", "qlcplus")
        eigen = self._profil("Testwerk", "Par 7", "user")
        self._spielen(_datei())
        self.assertEqual([i for i, _s in self._quellen("Par 7")], [imp, eigen])
        self.assertEqual(sorted(self._suche("Par 7")),
                         sorted([imp, eigen]))

    def test_builtin_wird_nie_abgeloest(self):
        b = self._profil("Testwerk", "Par 7", "builtin")
        self._spielen(_datei())
        self.assertEqual(self._quellen("Par 7"), [(b, "builtin")])
        self.assertEqual(FDB.abgeloeste_profil_ids(), set())


class C_BestehenderPatchLaedtWeiter(_Basis):

    def setUp(self):
        super().setUp()
        from src.core.show import show_file
        self.sf = show_file
        self.alt = self._profil("Testwerk", "Par 7", "qlcplus")
        self._spielen(_datei())
        self.neu = self._lightos_id()
        show_file._ladeprobleme.clear()
        self.addCleanup(show_file._ladeprobleme.clear)

    def _patch(self, pid: int) -> dict:
        return {"fid": 1, "label": "Par", "fixture_profile_id": pid,
                "mode_name": "3 Kanal", "universe": 1, "address": 1,
                "channel_count": 3, "manufacturer_name": "Testwerk",
                "fixture_name": "Par 7", "fixture_type": "par"}

    def test_patch_auf_altem_import_behaelt_id_und_kanaele(self):
        pf = self.sf._patched_fixture_from_data(self._patch(self.alt), 1)
        self.assertEqual(pf.fixture_profile_id, self.alt)
        self.assertEqual(self.sf.letzte_ladeprobleme(), [])
        modi = {m.name: m for m in FDB.get_modes(self.alt)}
        self.assertIn("3 Kanal", modi)
        self.assertEqual([c.attribute for c in FDB.get_channels(modi["3 Kanal"].id)],
                         ["color_r", "color_g", "color_b"])

    def test_fremde_id_landet_beim_lightos_profil_ohne_dubletten_warnung(self):
        pf = self.sf._patched_fixture_from_data(self._patch(987654), 1)
        self.assertEqual(pf.fixture_profile_id, self.neu)
        self.assertEqual([p for p in self.sf.letzte_ladeprobleme() if "Dublette" in p], [])


if __name__ == "__main__":
    unittest.main()
