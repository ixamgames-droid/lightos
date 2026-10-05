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

    def test_fixture_browser_stellt_import_unter_eigenen_knoten(self):
        """Nachbesserung: der abgeloeste Import ist im Browser nicht weg,
        sondern unter einem eingeklappten Knoten bewusst waehlbar — mit
        Hinweis auf das abloesende Profil. Die Suche blendet ihn aus."""
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication([])  # noqa: F841
        from src.ui.widgets.fixture_browser import ABGELOEST_KNOTEN, FixtureBrowserDialog
        from PySide6.QtCore import Qt
        alt = self._profil("Testwerk", "Par 7", "qlcplus")
        anderes = self._profil("Testwerk", "Bar 9", "qlcplus")
        self._spielen(_datei())
        neu = self._lightos_id()

        def ids(wurzeln) -> list[int]:
            out, stack = [], list(wurzeln)
            while stack:
                it = stack.pop()
                v = it.data(0, Qt.ItemDataRole.UserRole)
                if v is not None:
                    out.append(int(v))
                stack.extend(it.child(j) for j in range(it.childCount()))
            return sorted(out)

        d = FixtureBrowserDialog(1)
        self.addCleanup(d.deleteLater)
        oben = [d._tree.topLevelItem(i) for i in range(d._tree.topLevelItemCount())]
        knoten = [it for it in oben if it.text(0) == ABGELOEST_KNOTEN]
        self.assertEqual(len(knoten), 1, [it.text(0) for it in oben])
        (knoten,) = knoten
        self.assertIs(oben[-1], knoten)                 # ganz unten
        self.assertFalse(knoten.isExpanded())           # eingeklappt
        self.assertEqual(ids([knoten]), [alt])
        self.assertEqual(ids(it for it in oben if it is not knoten),
                         sorted([neu, anderes]))
        kind = knoten.child(0)
        self.assertIn("LightOS-Profil", kind.toolTip(0))
        self.assertIn(f"Profil {neu}", kind.toolTip(0))
        # bewusst waehlbar: Auswahl laedt den alten Import samt Modus
        d._tree.setCurrentItem(kind)
        self.assertEqual(d._selected_profile.id, alt)
        self.assertEqual(d._combo_mode.currentText(), "3 Kanal (3ch)")
        # Suche: nur das LightOS-Profil, kein Knoten
        d._search.setText("Par 7")
        oben = [d._tree.topLevelItem(i) for i in range(d._tree.topLevelItemCount())]
        self.assertEqual(ids(oben), [neu])
        self.assertNotIn(ABGELOEST_KNOTEN, [it.text(0) for it in oben])

    def test_ohne_abloesung_kein_knoten(self):
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication([])  # noqa: F841
        from src.ui.widgets.fixture_browser import ABGELOEST_KNOTEN, FixtureBrowserDialog
        self._profil("Testwerk", "Bar 9", "qlcplus")
        d = FixtureBrowserDialog(1)
        self.addCleanup(d.deleteLater)
        self.assertNotIn(ABGELOEST_KNOTEN, [d._tree.topLevelItem(i).text(0)
                                            for i in range(d._tree.topLevelItemCount())])

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


class D_BearbeiteterImportWirdNieAbgeloest(_Basis):
    """Nachbesserung: speichert der Fixture-Editor einen QLC+-Import an Ort und
    Stelle, ist der ein eigenes Profil — Marke in ``herkunft``, ``source``
    bleibt ``qlcplus`` (Spider-Dual-Tilt-Erkennung)."""

    def _im_editor_speichern(self, pid: int, aendern: bool = True) -> None:
        from unittest import mock
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication([])  # noqa: F841
        import src.ui.widgets.fixture_editor as ed
        meldungen: list = []
        with mock.patch.object(ed, "engine", lambda: self.eng), \
                mock.patch.object(ed.QMessageBox, "information"), \
                mock.patch.object(ed.QMessageBox, "warning",
                                  lambda *a, **k: meldungen.append(a[1:3]) or 0):
            dlg = ed.FixtureEditorDialog(fixture_id=pid)
            self.addCleanup(dlg.deleteLater)
            if aendern:
                dlg._spin_power.setValue(dlg._spin_power.value() + 5)
            dlg._save()
        self.assertEqual(meldungen, [])

    def _herkunft(self, pid: int) -> str:
        with Session(self.eng) as s:
            return s.get(FixtureProfile, pid).herkunft or ""

    def test_bearbeiteter_import_verdeckt_die_datei_wie_ein_eigenes(self):
        """Review FM-63: wie ``user`` — kein LightOS-Profil daneben, sonst
        stuende das Geraet dauerhaft doppelt in der Bibliothek."""
        alt = self._profil("Testwerk", "Par 7", "qlcplus")
        self._im_editor_speichern(alt)
        self.assertTrue(FDB.ist_bearbeitet(self._herkunft(alt)))
        self._spielen(_datei())
        self.assertEqual(self._quellen("Par 7"), [(alt, "qlcplus")])
        self.assertEqual(BF.LETZTES_EINSPIELEN["verdeckt"], ["Testwerk / Par 7"])
        self.assertEqual(FDB.abgeloeste_profil_ids(), set())
        self.assertEqual(self._suche("Par 7"), [alt])

    def test_spaeter_bearbeitet_bleibt_sichtbar_lightos_wird_weiter_gepflegt(self):
        alt = self._profil("Testwerk", "Par 7", "qlcplus")
        self._spielen(_datei())
        neu = self._lightos_id()
        self._im_editor_speichern(alt)
        self.assertEqual(FDB.get_fixture(alt).source, "qlcplus")
        self.assertEqual(FDB.abgeloeste_profil_ids(), set())
        self.assertEqual(sorted(self._suche("Par 7")), sorted([alt, neu]))
        d = _datei(leistung_w=90)
        self._spielen(d)
        self.assertEqual(BF.LETZTES_EINSPIELEN["aktualisiert"], ["Testwerk / Par 7"])
        self.assertEqual(FDB.get_fixture(neu).power_w, 90)

    def test_speichern_ohne_aenderung_setzt_keine_marke(self):
        alt = self._profil("Testwerk", "Par 7", "qlcplus")
        self._im_editor_speichern(alt, aendern=False)
        self.assertFalse(FDB.ist_bearbeitet(self._herkunft(alt)))
        self._spielen(_datei())
        self.assertEqual(FDB.abgeloeste_profil_ids(), {alt})

    def test_unbearbeiteter_import_wird_abgeloest(self):
        """Gegenprobe: ohne Speichern im Editor greift die Abloesung."""
        alt = self._profil("Testwerk", "Par 7", "qlcplus")
        self.assertFalse(FDB.ist_bearbeitet(self._herkunft(alt)))
        self._spielen(_datei())
        self.assertEqual(FDB.abgeloeste_profil_ids(), {alt})

    def test_spider_dual_tilt_erkennung_bleibt(self):
        pid = self._profil("Testwerk", "Spider 2", "qlcplus", modus="Std",
                           attrs=("pan", "tilt", "color_r", "color_g", "color_r", "color_g"))
        self._im_editor_speichern(pid)
        prof = FDB.get_fixture(pid)
        chans = FDB.get_channels(FDB.get_modes(pid)[0].id)
        self.assertTrue(FDB.ist_bearbeitet(prof.herkunft))
        self.assertTrue(FDB.should_auto_mark_dual_tilt(prof, chans))

    def test_marke_erhaelt_vorhandene_herkunft(self):
        from src.core.database import bibliothek_format as bf
        d = _datei()
        voll = {k: d[k] for k in bf.HERKUNFT_SCHLUESSEL}
        p = FixtureProfile(name="x", source="qlcplus",
                           herkunft=json_dumps(voll))
        FDB.als_bearbeitet_markieren(p)
        self.assertTrue(FDB.ist_bearbeitet(p.herkunft))
        self.assertEqual(bf.gespeicherte_herkunft(p), voll)
        q = FixtureProfile(name="y", source="qlcplus", herkunft="")
        FDB.als_bearbeitet_markieren(q)
        self.assertIsNone(bf.gespeicherte_herkunft(q))   # Ableitung wie bisher


def json_dumps(d) -> str:
    import json
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


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

    def _fremd(self, modus: str, kanaele: int):
        d = self._patch(987654)
        d.update(mode_name=modus, channel_count=kanaele)
        return self.sf._patched_fixture_from_data(d, 1)

    def test_fremde_id_mit_modus_des_lightos_profils_landet_dort(self):
        pf = self._fremd("4-Kanal", 4)
        self.assertEqual(pf.fixture_profile_id, self.neu)
        self.assertEqual(self.sf.letzte_ladeprobleme(), [])

    def test_fremde_id_mit_modus_nur_im_import_landet_beim_import(self):
        """Review FM-63 (HOCH): das LightOS-Profil hat „3 Kanal“ nicht —
        blind genommen haette `_resolve_mode` still den 4-Kanal-Modus gefahren."""
        pf = self._fremd("3 Kanal", 3)
        self.assertEqual(pf.fixture_profile_id, self.alt)
        self.assertEqual(self.sf.letzte_ladeprobleme(), [])

    def test_nur_kanalzahl_passt(self):
        pf = self._fremd("Anders benannt", 3)
        self.assertEqual(pf.fixture_profile_id, self.alt)
        self.assertTrue(any("NICHT" in p and "Anders benannt" in p
                            for p in self.sf.letzte_ladeprobleme()),
                        self.sf.letzte_ladeprobleme())

    def test_modus_fehlt_ueberall_wird_gemeldet(self):
        pf = self._fremd("9 Kanal", 9)
        self.assertEqual(pf.fixture_profile_id, self.neu)
        self.assertTrue(any("9 Kanal" in p and "NICHT" in p
                            for p in self.sf.letzte_ladeprobleme()),
                        self.sf.letzte_ladeprobleme())

    def test_echte_dublette_wird_weiter_gewarnt(self):
        """Nur das Paar LightOS + abgeloester Import ist ausgenommen."""
        self._profil("Testwerk", "Par 7", "builtin", modus="4-Kanal",
                     attrs=("intensity", "color_r", "color_g", "color_b"))
        pf = self._fremd("4-Kanal", 4)
        self.assertEqual(pf.fixture_profile_id, self.neu)
        self.assertTrue(any("Dublette" in p for p in self.sf.letzte_ladeprobleme()),
                        self.sf.letzte_ladeprobleme())


class E_ShowbuilderStrict(_Basis):
    """Review FM-63 (NIEDRIG): gleicher short_name bei LightOS-Profil und dem
    Import, den es abloest -> keine Mehrdeutigkeit, auch im strict-Modus."""

    def _builder(self, strict: bool):
        from src.core.show.showbuilder import ShowBuilder
        b = object.__new__(ShowBuilder)
        b._strict_profiles = strict
        b._ambig_warned = set()
        return b

    def test_kein_buildfehler_bei_abgeloestem_import(self):
        alt = self._profil("Testwerk", "Par 7", "qlcplus")
        with Session(self.eng) as s:
            s.get(FixtureProfile, alt).short_name = "PAR7LOS"
            s.commit()
        self._spielen(_datei())
        neu = self._lightos_id()
        pid, *_ = self._builder(strict=True)._lookup_profile("PAR7LOS")
        self.assertEqual(pid, neu)

    def test_echte_mehrdeutigkeit_bleibt_buildfehler(self):
        from src.core.show.showbuilder import BuildError
        self._profil("Testwerk", "Bar 9", "qlcplus")
        b = self._profil("Testwerk", "Bar 10", "qlcplus")
        with Session(self.eng) as s:
            s.get(FixtureProfile, b).short_name = "Bar 9"
            s.commit()
        with self.assertRaises(BuildError):
            self._builder(strict=True)._lookup_profile("Bar 9")


if __name__ == "__main__":
    unittest.main()
