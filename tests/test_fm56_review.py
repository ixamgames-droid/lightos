"""FM-56 Review (Etappe 1): Befunde der Gegenpruefung, je einer ein Test.

1. Werkzeug-Index: ``tools/bibliothek_profil.py`` steht in ``tools/README.md``
   (geprueft von ``tests/test_tools_index.py``).
2. Kaputte Dateien (falsche Typen, falsche Kodierung) brechen weder
   ``pruefe`` noch das Einspielen beim Start ab — sie werden Befund.
3.–5. Die Herkunft geht nie verloren: Import/Export einer QLC+-Datei, Editor-
   Export eines QLC+-Profils, lightos-Profil ohne Datei. Fehlt sie, bricht der
   Export ab, statt „eigen“ zu erfinden.
6. Editor-Import fragt vor dem Verwerfen und meldet den Erfolg.
7. ``bibliothek_profil.py import`` in eine neue DB seedet zuerst.
8. Einspielen nur fuer geaenderte/neue Dateien (Stempel je Datei).
9. ``export`` mit unbekannter ID -> FEHLER-Zeile, kein Traceback.
10. Neben gleichnamigem user/qlcplus-Profil wird nichts angelegt.
11. Konverter kuerzt zu lange Namen und macht doppelte Modi eindeutig.
12. Editor-Export uebernimmt notizen, viz_model, hersteller_kurz.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine, select          # noqa: E402
from sqlalchemy.orm import Session                    # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.database import bibliothek_format as BF   # noqa: E402
from src.core.database import fixture_db as FDB         # noqa: E402
from src.core.database.models import (FixtureProfile, Manufacturer,  # noqa: E402
                                      create_all_idempotent)
from src.core.database.qxf_import import QXF_NS        # noqa: E402
from test_fm56_bibliothek_format import _minimal       # noqa: E402

QLC_HERKUNFT = {"art": "qlcplus", "lizenz": "Apache-2.0", "urheber": "QLC+ Leute",
                "original": "resources/fixtures/T/T-Par.qxf", "geaendert": "umgebaut"}


def _db():
    eng = create_engine("sqlite://")
    create_all_idempotent(eng)
    return eng


class _Tmp:
    def _tmp(self) -> str:
        d = tempfile.mkdtemp(prefix="lightos_fm56r_")
        self.addCleanup(shutil.rmtree, d, True)
        return d


class B01WerkzeugIndex(unittest.TestCase):
    def test_bibliothek_profil_im_index(self):
        with open(os.path.join(REPO, "tools", "README.md"), encoding="utf-8") as fh:
            self.assertIn("bibliothek_profil.py", fh.read())


class B02KaputteDateien(unittest.TestCase, _Tmp):
    FAELLE = {
        "typ_liste": lambda d: d.update(typ=["par"]),
        "attribut_dict": lambda d: d["modi"][0]["kanaele"][0].update(attribut={"a": 1}),
        "attribut_int_mit_segment": lambda d: d["modi"][0]["kanaele"][0].update(
            attribut=5, segment=0),
        "art_liste": lambda d: d["herkunft"].update(art=["qlcplus"]),
        "lizenz_liste": lambda d: d["herkunft"].update(lizenz=["eigen"]),
        "bereich_art_liste": lambda d: d["modi"][0]["kanaele"][4]["bereiche"][0].update(
            art=["open"]),
        "aufloesung_liste": lambda d: d["modi"][0]["kanaele"][0].update(aufloesung=["8bit"]),
    }

    def test_pruefe_wirft_nie(self):
        for name, aendern in self.FAELLE.items():
            with self.subTest(name):
                d = _minimal()
                aendern(d)
                self.assertTrue(BF.pruefe(d, "x.json"))

    def test_latin1_datei_ist_befund(self):
        pfad = os.path.join(self._tmp(), "x.json")
        with open(pfad, "wb") as fh:
            text = json.dumps(_minimal(modell="Gerät"), ensure_ascii=False)
            fh.write(text.replace("→", "->").encode("latin-1"))
        with self.assertRaises(BF.ProfilFehler):
            BF.lade_datei(pfad)

    def test_einspielen_ueberspringt_und_spielt_den_rest_ein(self):
        wurzel = self._tmp()
        BF.schreibe(_minimal(), os.path.join(wurzel, BF.dateiname("Testwerk", "Par 7")))
        kaputt = _minimal(modell="Par 8")
        kaputt["typ"] = ["par"]
        os.makedirs(os.path.join(wurzel, "testwerk"), exist_ok=True)
        with open(os.path.join(wurzel, "testwerk", "par-8.json"), "w", encoding="utf-8") as fh:
            json.dump(kaputt, fh)
        with open(os.path.join(wurzel, "testwerk", "par-9.json"), "wb") as fh:
            fh.write('{"modell": "Gerät"}'.encode("latin-1"))
        eng = _db()
        with Session(eng) as s:
            BF.einspielen_wenn_noetig(s, wurzel)
            s.commit()
            namen = [p.name for p in s.scalars(select(FixtureProfile))]
        self.assertEqual(namen, ["Par 7"])
        self.assertEqual(len(BF.LETZTES_EINSPIELEN["fehler"]), 2)


class B03bis05HerkunftBleibt(unittest.TestCase, _Tmp):

    def test_import_export_behaelt_qlc_herkunft(self):
        eng = _db()
        pid = BF.importiere(_minimal(herkunft=dict(QLC_HERKUNFT)), engine=eng)
        aus = BF.exportiere(pid, engine=eng)
        self.assertEqual(aus["herkunft"], QLC_HERKUNFT)
        self.assertEqual(aus["quelle"], _minimal()["quelle"])
        self.assertEqual(aus["autor"], "LightOS")

    def test_lightos_profil_ohne_datei_behaelt_herkunft(self):
        wurzel = self._tmp()
        pfad = os.path.join(wurzel, BF.dateiname("Testwerk", "Par 7"))
        BF.schreibe(_minimal(herkunft=dict(QLC_HERKUNFT)), pfad)
        eng = _db()
        with Session(eng) as s:
            BF.einspielen(s, wurzel)
            s.commit()
            pid = s.scalars(select(FixtureProfile.id)).one()
        os.remove(pfad)
        self.assertEqual(BF.exportiere(pid, engine=eng)["herkunft"], QLC_HERKUNFT)

    def test_lightos_profil_ganz_ohne_herkunft_bricht_ab(self):
        eng = _db()
        with Session(eng) as s:
            m = Manufacturer(name="Testwerk", short_name="TW")
            s.add(FixtureProfile(manufacturer=m, name="Weg", short_name="W",
                                 source="lightos",
                                 provenance="LightOS-Profil v1 · qlcplus · Apache-2.0 · X"))
            s.commit()
            pid = s.scalars(select(FixtureProfile.id)).one()
        with self.assertRaises(BF.ProfilFehler):
            BF.exportiere(pid, engine=eng)

    def test_editor_export_eines_qlc_profils(self):
        from PySide6.QtWidgets import QApplication
        from src.ui.widgets import fixture_editor as E
        QApplication.instance() or QApplication([])
        eng = _db()
        with Session(eng) as s:
            m = Manufacturer(name="QlcCo", short_name="QLC")
            p = FixtureProfile(manufacturer=m, name="Spot", short_name="SPOT",
                               fixture_type="moving_head", source="qlcplus",
                               provenance="Q Light Controller Plus 4.12 · Autorin")
            s.add(p)
            s.commit()
            pid = p.id
        with mock.patch.object(E, "engine", return_value=eng), \
                mock.patch.object(E.QMessageBox, "warning"):
            dlg = E.FixtureEditorDialog(fixture_id=pid)
            dlg._tabs.widget(0).channels = [{"name": "Dim", "attribute": "intensity",
                                             "default": 0, "highlight": 255}]
            dlg._tabs.widget(0)._rebuild_rows()
            ziel = os.path.join(self._tmp(), "spot.json")
            self.assertEqual(dlg._lightos_export(ziel), ziel)
            dlg.deleteLater()
        d = BF.lade_datei(ziel)
        self.assertEqual((d["herkunft"]["art"], d["herkunft"]["lizenz"]),
                         ("qlcplus", "Apache-2.0"))
        self.assertIn("Autorin", d["herkunft"]["urheber"])


class B06EditorImportFragt(unittest.TestCase, _Tmp):

    def test_fragt_vor_verwerfen_und_meldet_erfolg(self):
        from PySide6.QtWidgets import QApplication, QMessageBox
        from src.ui.widgets import fixture_editor as E
        QApplication.instance() or QApplication([])
        eng = _db()
        datei = os.path.join(self._tmp(), "p.json")
        BF.schreibe(_minimal(), datei)
        with mock.patch.object(E, "engine", return_value=eng), \
                mock.patch.object(QMessageBox, "information") as info, \
                mock.patch.object(QMessageBox, "question",
                                  return_value=QMessageBox.StandardButton.No) as frage:
            dlg = E.FixtureEditorDialog()
            dlg._edit_name.setText("Mein Geraet")
            self.assertIsNone(dlg._lightos_import(datei))     # abgelehnt
            self.assertEqual(frage.call_count, 1)
            frage.return_value = QMessageBox.StandardButton.Yes
            pid = dlg._lightos_import(datei)
            self.assertIsNotNone(pid)
            self.assertEqual(info.call_count, 1)
            self.assertIn("Par 7", info.call_args[0][2])
            dlg.deleteLater()


class B07ImportSeedet(unittest.TestCase, _Tmp):

    def test_import_in_neue_db_seedet_zuerst(self):
        import bibliothek_profil as T
        wurzel = self._tmp()
        datei = os.path.join(wurzel, "p.json")
        BF.schreibe(_minimal(), datei)
        db = os.path.join(wurzel, "neu.db")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(T.main(["import", datei, "--db", db]), 0)
        eng = FDB.get_engine(db)
        self.addCleanup(eng.dispose)
        with Session(eng) as s:
            n = len(s.scalars(select(FixtureProfile)
                              .where(FixtureProfile.source == "builtin")).all())
        self.assertGreaterEqual(n, 30)


class B08StempelJeDatei(unittest.TestCase, _Tmp):

    def test_nur_geaenderte_datei_wird_eingespielt(self):
        wurzel = self._tmp()
        a = _minimal()
        b = _minimal(modell="Par 8", kurzname="PAR8")
        for d in (a, b):
            BF.schreibe(d, os.path.join(wurzel, BF.dateiname(d["hersteller"], d["modell"])))
        eng = _db()
        with Session(eng) as s:
            BF.einspielen_wenn_noetig(s, wurzel)
            s.commit()
        b["leistung_w"] = 99
        BF.schreibe(b, os.path.join(wurzel, BF.dateiname("Testwerk", "Par 8")))
        gesehen = []
        echt = BF._abgleichen

        def zaehlen(s, daten, *a, **k):
            gesehen.append(daten["modell"])
            return echt(s, daten, *a, **k)
        with Session(eng) as s, mock.patch.object(BF, "_abgleichen", zaehlen):
            self.assertTrue(BF.einspielen_wenn_noetig(s, wurzel))
            s.commit()
            self.assertEqual(gesehen, ["Par 8"])
            self.assertFalse(BF.einspielen_wenn_noetig(s, wurzel))
            # aus der DB geloescht -> beim naechsten Lauf wieder da
            s.delete(s.scalars(select(FixtureProfile)
                               .where(FixtureProfile.name == "Par 7")).one())
            s.commit()
            gesehen.clear()
            BF.einspielen_wenn_noetig(s, wurzel)
            s.commit()
            self.assertEqual(gesehen, ["Par 7"])


class B09ExportFehlerzeile(unittest.TestCase, _Tmp):

    def test_unbekannte_id(self):
        import bibliothek_profil as T
        db = os.path.join(self._tmp(), "t.db")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(T.main(["export", "--id", "99999", "--db", db]), 1)
        self.assertIn("FEHLER", err.getvalue())


class B10KeineDubletteNebenEigenem(unittest.TestCase, _Tmp):

    def test_user_profil_verdeckt_die_datei(self):
        eng = _db()
        BF.importiere(_minimal(), engine=eng)
        wurzel = self._tmp()
        BF.schreibe(_minimal(), os.path.join(wurzel, BF.dateiname("Testwerk", "Par 7")))
        with Session(eng) as s:
            BF.einspielen(s, wurzel)
            s.commit()
            self.assertEqual([p.source for p in s.scalars(select(FixtureProfile))], ["user"])
        self.assertEqual(len(BF.LETZTES_EINSPIELEN["verdeckt"]), 1)


def _qxf_lang() -> str:
    lang = "Sehr langer Bereichsname " * 5
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>Lang</Model>
 <Type>Color Changer</Type>
 <Channel Name="Makro" Preset="">
  <Capability Min="0" Max="127">{lang}</Capability>
  <Capability Min="128" Max="255">kurz</Capability>
 </Channel>
 <Mode Name="1 Channel"><Channel Number="0">Makro</Channel></Mode>
 <Mode Name="1 Channel"><Channel Number="0">Makro</Channel></Mode>
</FixtureDefinition>
"""


class B11KonverterKuerzt(unittest.TestCase, _Tmp):

    def test_lange_namen_und_doppelte_modi(self):
        pfad = os.path.join(self._tmp(), "lang.qxf")
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write(_qxf_lang())
        d = BF.qxf_zu_daten(pfad)
        self.assertEqual(BF.pruefe(d), [])
        self.assertEqual([m["name"] for m in d["modi"]], ["1 Channel", "1 Channel (2)"])
        self.assertLessEqual(len(d["modi"][0]["kanaele"][0]["bereiche"][0]["name"]), 80)
        self.assertIn("gekuerzt", d["herkunft"]["geaendert"])
        self.assertIn("eindeutig", d["herkunft"]["geaendert"])


class B12EditorExportVollstaendig(unittest.TestCase, _Tmp):

    def test_notizen_viz_model_hersteller_kurz(self):
        from PySide6.QtWidgets import QApplication
        from src.ui.widgets import fixture_editor as E
        QApplication.instance() or QApplication([])
        eng = _db()
        pid = BF.importiere(_minimal(notizen="Achtung Lüfter", viz_model="par",
                                     hersteller_kurz="TWK"), engine=eng)
        with mock.patch.object(E, "engine", return_value=eng):
            dlg = E.FixtureEditorDialog(fixture_id=pid)
            ziel = os.path.join(self._tmp(), "x.json")
            self.assertEqual(dlg._lightos_export(ziel), ziel)
            dlg.deleteLater()
        d = BF.lade_datei(ziel)
        self.assertEqual((d.get("notizen"), d.get("viz_model"), d.get("hersteller_kurz")),
                         ("Achtung Lüfter", "par", "TWK"))


class ApacheLizenzBleibt(unittest.TestCase):
    """Die Bibliothek braucht den Apache-Text fuer QLC+-basierte Profile —
    auch wenn keine 3D-Modelle aus QLC+ mehr mitkommen."""

    def test_apache_text_liegt_bei(self):
        self.assertTrue(os.path.isfile(os.path.join(REPO, "licenses", "Apache-2.0.txt")))


if __name__ == "__main__":
    unittest.main()
