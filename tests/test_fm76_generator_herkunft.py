"""FM-76: der Fixture Generator traegt die Herkunft einer geladenen Vorlage
bis zum Speichern mit.

Befund: „LightOS-Profil (.json) laden…“ (``_import_profil`` ->
``model_from_daten``) und „QLC+ (.qxf) importieren…“ (``_import_qxf`` ->
``model_from_qxf``) uebernahmen den ganzen Geraeteinhalt einer fremden
Vorlage; gespeichert wurde ueber ``fixture_db.create_user_profile`` OHNE
Herkunft, ``bibliothek_format.herkunft_fuer`` meldete „eigen“. Eine
Bibliotheksdatei mit Lizenz (``cameo/auro-spot-100.json``, art ``qlcplus``,
Apache-2.0) verlor so ihre Herkunfts-/Lizenzangabe.

Gemessen wird am gespeicherten Profil in einer Wegwerf-DB: was meldet
``herkunft_fuer`` dafuer? Dateidialoge und Meldungen sind ersetzt.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                     # noqa: E402
from sqlalchemy.orm import Session                             # noqa: E402

from src.core.database import bibliothek_format as BF          # noqa: E402
from src.core.database import fixture_db as FDB                # noqa: E402
from src.core.database.fixture_db import get_engine            # noqa: E402
from src.core.database.models import (                         # noqa: E402
    FixtureProfile, Manufacturer, create_all_idempotent)
from src.core.database.qxf_import import QXF_NS                # noqa: E402
from src.ui.widgets import fixture_generator as FG             # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                               # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets        # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AURO = os.path.join(_REPO, "fixtures", "bibliothek", "cameo", "auro-spot-100.json")
_HANDBUCH = os.path.join(_REPO, "fixtures", "bibliothek", "ignition",
                         "2bright-pint-tw200-ip-mk-ii.json")

_QXF = f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Creator><Name>Q Light Controller Plus</Name><Version>4.12.3</Version>
  <Author>Testautorin</Author></Creator>
 <Manufacturer>TestCo</Manufacturer>
 <Model>FM76 Par</Model>
 <Type>Color Changer</Type>
 <Channel Name="Dimmer" Preset="IntensityMasterDimmer"/>
 <Channel Name="Red" Preset="IntensityRed"/>
 <Mode Name="2ch">
  <Channel Number="0">Dimmer</Channel>
  <Channel Number="1">Red</Channel>
 </Mode>
</FixtureDefinition>
"""


class _Fall(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fm76_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.engine = get_engine(os.path.join(self.tmp, "fixtures.db"))
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        p = mock.patch.object(FDB, "_engine", self.engine)
        p.start()
        self.addCleanup(p.stop)
        self.meldung = {}
        for methode in ("information", "warning", "question"):
            pm = mock.patch.object(FG.QMessageBox, methode)
            self.meldung[methode] = pm.start()
            self.addCleanup(pm.stop)
        self.meldung["question"].return_value = FG.QMessageBox.StandardButton.Yes

    # ── Hilfen ───────────────────────────────────────────────────────────
    def _dialog(self, model=None):
        dlg = FG.FixtureGeneratorDialog(model=model)
        self.addCleanup(dlg.deleteLater)
        return dlg

    def _datei_laden(self, dlg, quelle: str, *, modell: str) -> None:
        """Bibliotheksdatei unter neuem Modellnamen in den Temp-Bereich
        kopieren und ueber den Knopf „LightOS-Profil (.json) laden…“ laden."""
        with open(quelle, encoding="utf-8") as fh:
            daten = json.load(fh)
        daten["modell"] = modell
        pfad = os.path.join(self.tmp, "vorlage.json")
        with open(pfad, "w", encoding="utf-8") as fh:
            json.dump(daten, fh, ensure_ascii=False)
        with mock.patch.object(FG.QFileDialog, "getOpenFileName",
                               return_value=(pfad, "")):
            dlg._import_profil()
        self.assertEqual(self.meldung["warning"].call_args_list, [])

    def _qxf_laden(self, dlg, name="FM76-Par.qxf") -> str:
        pfad = os.path.join(self.tmp, name)
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write(_QXF)
        with mock.patch.object(FG.QFileDialog, "getOpenFileName",
                               return_value=(pfad, "")):
            dlg._import_qxf()
        self.assertEqual(self.meldung["warning"].call_args_list, [])
        return pfad

    def _speichern(self, dlg) -> int:
        dlg._save()
        self.assertEqual(self.meldung["warning"].call_args_list, [],
                         "Speichern wurde abgebrochen")
        self.assertIsNotNone(dlg.saved_id)
        return dlg.saved_id

    def _herkunft(self, profil_id: int) -> tuple[dict, str]:
        with Session(self.engine) as s:
            prof = s.get(FixtureProfile, profil_id)
            return BF.herkunft_fuer(prof), prof.herkunft or ""

    def _anzahl_profile(self) -> int:
        with Session(self.engine) as s:
            return s.query(FixtureProfile).count()


class GeladeneBibliotheksdateiTest(_Fall):

    def test_qlcplus_vorlage_behaelt_lizenz(self):
        """Der Befund: Auro Spot (art qlcplus, Apache-2.0) laden, speichern —
        das neue Profil traegt Herkunft, Urheber und Original der Datei."""
        vorlage = BF.lade_datei(_AURO)
        dlg = self._dialog()
        self._datei_laden(dlg, _AURO, modell="Auro Spot FM76")
        pid = self._speichern(dlg)
        h, gespeichert = self._herkunft(pid)
        self.assertTrue(gespeichert, "keine Herkunft in der DB gespeichert")
        self.assertEqual(h["herkunft"]["art"], "qlcplus")
        self.assertEqual(h["herkunft"]["lizenz"], "Apache-2.0")
        self.assertEqual(h["herkunft"]["urheber"], vorlage["herkunft"]["urheber"])
        self.assertEqual(h["herkunft"]["original"], vorlage["herkunft"]["original"])
        self.assertEqual(h["quelle"], vorlage["quelle"])
        self.assertIn(BF.GENERATOR_VERMERK, h["herkunft"]["geaendert"])
        self.assertTrue(h["herkunft"]["geaendert"].startswith(
            vorlage["herkunft"]["geaendert"]))
        # Der Pruefvermerk der Vorlage gilt nicht fuer den neuen Inhalt.
        self.assertFalse(h["geprueft"]["ok"])

    def test_stark_umgebaut_bleibt_herkunft_der_vorlage(self):
        """Lizenzpflicht folgt dem Ursprung: Hersteller/Modell neu, Modi
        ersetzt — die Herkunft bleibt die der Vorlage."""
        dlg = self._dialog()
        self._datei_laden(dlg, _AURO, modell="Auro Spot FM76")
        dlg._edit_mfr.setText("Eigenbau")
        dlg._edit_model.setText("Ganz anderes Gerät")
        dlg._edit_short.setText("ANDERS")
        dlg._sync_all()
        dlg._model.modes = [FG.GenMode("Neu", [FG.GenChannel("Dimmer", "intensity")])]
        dlg._reload_modes()
        dlg._revalidate()
        pid = self._speichern(dlg)
        h, _ = self._herkunft(pid)
        self.assertEqual((h["herkunft"]["art"], h["herkunft"]["lizenz"]),
                         ("qlcplus", "Apache-2.0"))

    def test_handbuch_vorlage_behaelt_quelle(self):
        """Auch eine nicht-fremde Herkunft (Herstellerhandbuch) reist mit,
        statt zu „eigenes Profil“ zu werden."""
        vorlage = BF.lade_datei(_HANDBUCH)
        dlg = self._dialog()
        self._datei_laden(dlg, _HANDBUCH, modell="Pint FM76")
        pid = self._speichern(dlg)
        h, _ = self._herkunft(pid)
        self.assertEqual(h["herkunft"], vorlage["herkunft"])
        self.assertEqual(h["quelle"], vorlage["quelle"])

    def test_hinweisliste_zeigt_die_herkunft(self):
        dlg = self._dialog()
        self._datei_laden(dlg, _AURO, modell="Auro Spot FM76")
        text = dlg._issues.toPlainText()
        self.assertIn("Herkunft der Vorlage: QLC+, Lizenz Apache-2.0", text)
        self.assertIn("übernommen", text)


    def test_zweite_vorlage_ersetzt_die_herkunft(self):
        """Gegenpruefung: im selben Dialog erst Auro (QLC+, Apache-2.0), dann
        die Handbuch-Vorlage laden — die Herkunft der ersten darf nicht
        kleben bleiben."""
        vorlage = BF.lade_datei(_HANDBUCH)
        dlg = self._dialog()
        self._datei_laden(dlg, _AURO, modell="Auro Spot FM76")
        self._datei_laden(dlg, _HANDBUCH, modell="Pint FM76")
        self.assertEqual(dlg._model.herkunft["herkunft"], vorlage["herkunft"])
        pid = self._speichern(dlg)
        h, _ = self._herkunft(pid)
        self.assertEqual(h["herkunft"], vorlage["herkunft"])
        self.assertEqual(h["quelle"], vorlage["quelle"])
        self.assertNotEqual(h["herkunft"].get("art"), "qlcplus")
        self.assertNotIn("Apache-2.0", json.dumps(h))

    def test_qxf_nach_vorlage_traegt_qxf_herkunft(self):
        dlg = self._dialog()
        self._datei_laden(dlg, _AURO, modell="Auro Spot FM76")
        self._qxf_laden(dlg)
        self.assertEqual(dlg._model.herkunft["herkunft"]["original"],
                         "FM76-Par.qxf")
        pid = self._speichern(dlg)
        h, _ = self._herkunft(pid)
        self.assertEqual(h["herkunft"]["original"], "FM76-Par.qxf")
        self.assertIn("Testautorin", h["herkunft"]["urheber"])


class VermerkEinmaligTest(_Fall):

    def test_mit_vermerk_haengt_nur_einmal_an(self):
        vorlage = BF.lade_datei(_AURO)
        h = {k: vorlage[k] for k in BF.HERKUNFT_SCHLUESSEL}
        einmal = BF.mit_vermerk(h, BF.GENERATOR_VERMERK)
        zweimal = BF.mit_vermerk(einmal, BF.GENERATOR_VERMERK)
        self.assertEqual(
            zweimal["herkunft"]["geaendert"].count(BF.GENERATOR_VERMERK), 1)
        self.assertEqual(zweimal, einmal)

    def test_zweimal_im_generator_gespeichert_ein_vermerk(self):
        """Profil aus Auro speichern, wieder in den Generator laden und erneut
        speichern — der Generator-Vermerk steht trotzdem nur einmal da."""
        dlg = self._dialog()
        self._datei_laden(dlg, _AURO, modell="Auro Spot FM76")
        pid = self._speichern(dlg)
        modell = FG.model_from_profile(pid, engine=self.engine)
        modell.model = "Auro Spot FM76 zwei"
        zweit = self._dialog(modell)
        pid2 = self._speichern(zweit)
        self.assertNotEqual(pid2, pid)
        h, _ = self._herkunft(pid2)
        self.assertEqual(
            h["herkunft"]["geaendert"].count(BF.GENERATOR_VERMERK), 1)


class QxfImportTest(_Fall):

    def test_qxf_vorlage_traegt_qlcplus_herkunft(self):
        dlg = self._dialog()
        self._qxf_laden(dlg)
        pid = self._speichern(dlg)
        h, _ = self._herkunft(pid)
        self.assertEqual(h["herkunft"]["art"], "qlcplus")
        self.assertEqual(h["herkunft"]["lizenz"], "Apache-2.0")
        self.assertIn("Testautorin", h["herkunft"]["urheber"])
        self.assertIn("QLC+-Beitragende", h["herkunft"]["urheber"])
        self.assertEqual(h["herkunft"]["original"], "FM76-Par.qxf")
        self.assertIn("FM76-Par.qxf", h["quelle"]["titel"])
        self.assertIn(BF.GENERATOR_VERMERK, h["herkunft"]["geaendert"])

    def test_qxf_herkunft_wie_bibliotheks_import(self):
        """Dieselben Angaben wie der Bibliotheks-Konverter (``qxf_zu_daten``)
        fuer Quelle, Urheber und Original — keine zweite Lesart."""
        pfad = os.path.join(self.tmp, "FM76-Par.qxf")
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write(_QXF)
        konv = BF.qxf_zu_daten(pfad)
        modell = FG.model_from_qxf(pfad)
        for k in ("urheber", "original", "art", "lizenz"):
            self.assertEqual(modell.herkunft["herkunft"][k], konv["herkunft"][k])
        self.assertEqual(modell.herkunft["quelle"], konv["quelle"])


class FreiGebautTest(_Fall):

    def test_frisches_profil_bleibt_eigen(self):
        dlg = self._dialog()
        dlg._edit_mfr.setText("Eigenbau")
        dlg._edit_model.setText("FM76 frei")
        dlg._edit_short.setText("FREI")
        pid = self._speichern(dlg)
        h, gespeichert = self._herkunft(pid)
        self.assertEqual(gespeichert, "")
        self.assertEqual(h["herkunft"], {"art": "lightos", "lizenz": "eigen"})

    def test_neuer_dialog_traegt_keine_alte_herkunft(self):
        """Ein neu geoeffneter Generator (Default-Modell) beginnt ohne
        Herkunft — sie haengt am Modell, nicht am Dialog oder Modul."""
        alt = self._dialog()
        self._datei_laden(alt, _AURO, modell="Auro Spot FM76")
        neu = self._dialog()
        self.assertIsNone(neu._model.herkunft)
        self.assertEqual(neu._model.herkunft_fehlt, "")
        self.assertNotIn("Herkunft der Vorlage", neu._issues.toPlainText())


class OhneBelegbareHerkunftTest(_Fall):

    def test_vorlage_ohne_herkunft_wird_nicht_gespeichert(self):
        daten = BF.lade_datei(_AURO)
        for k in BF.HERKUNFT_SCHLUESSEL:
            daten.pop(k)
        daten["modell"] = "Ohne Herkunft"
        modell = FG.model_from_daten(daten)
        self.assertIsNone(modell.herkunft)
        self.assertTrue(modell.herkunft_fehlt)
        dlg = self._dialog(modell)
        self.assertIn("Herkunft der Vorlage nicht belegbar",
                      dlg._issues.toPlainText())
        vorher = self._anzahl_profile()
        dlg._save()
        self.assertIsNone(dlg.saved_id)
        self.assertEqual(self._anzahl_profile(), vorher)
        self.assertEqual(len(self.meldung["warning"].call_args_list), 1)
        titel, text = self.meldung["warning"].call_args.args[1:3]
        self.assertEqual(titel, "Herkunft nicht belegbar")
        self.assertIn("Lizenz- und Herkunftsangabe verlieren", text)
        self.assertIn("Es wurde nichts gespeichert", text)

    def test_profil_aus_db_ohne_belegbare_herkunft(self):
        """``model_from_profile``: ein Bibliotheksprofil ohne gespeicherte
        Herkunft und ohne Datei laedt den Inhalt, meldet aber den Mangel."""
        with Session(self.engine) as s:
            mfr = Manufacturer(name="FM76 Hersteller", short_name="FM76")
            prof = FixtureProfile(manufacturer=mfr, name="Nirgends belegt",
                                  short_name="NB", fixture_type="par",
                                  source=BF.SOURCE_LIGHTOS)
            s.add(prof)
            s.commit()
            pid = prof.id
        modell = FG.model_from_profile(pid, engine=self.engine)
        self.assertIsNone(modell.herkunft)
        self.assertIn("Herkunft unbekannt", modell.herkunft_fehlt)

    def test_profil_aus_db_traegt_seine_herkunft(self):
        dlg = self._dialog()
        self._datei_laden(dlg, _AURO, modell="Auro Spot FM76")
        pid = self._speichern(dlg)
        modell = FG.model_from_profile(pid, engine=self.engine)
        self.assertEqual(modell.herkunft_fehlt, "")
        self.assertEqual(modell.herkunft["herkunft"]["lizenz"], "Apache-2.0")


class CreateUserProfileTest(_Fall):

    def _payload(self, name):
        return FG.GeneratorModel(manufacturer="Eigenbau", model=name,
                                 modes=[FG.GenMode("M", [FG.GenChannel(
                                     "Dimmer", "intensity")])]).to_payload()

    def test_ohne_herkunft_wie_bisher(self):
        pid = FDB.create_user_profile(self._payload("Alt"), engine=self.engine)
        h, gespeichert = self._herkunft(pid)
        self.assertEqual(gespeichert, "")
        self.assertEqual(h["autor"], "eigenes Profil")

    def test_mit_herkunft_schreibt_sie(self):
        vorlage = BF.lade_datei(_AURO)
        herkunft = {k: vorlage[k] for k in BF.HERKUNFT_SCHLUESSEL}
        pid = FDB.create_user_profile(self._payload("Mit"), engine=self.engine,
                                      herkunft=herkunft)
        h, _ = self._herkunft(pid)
        self.assertEqual(h, herkunft)
        with Session(self.engine) as s:
            self.assertIn("Apache-2.0", s.get(FixtureProfile, pid).provenance)

    def test_ungueltige_herkunft_wird_abgelehnt(self):
        vorher = self._anzahl_profile()
        with self.assertRaises(ValueError):
            FDB.create_user_profile(
                self._payload("Kaputt"), engine=self.engine,
                herkunft={"herkunft": {"art": "qlcplus", "lizenz": "eigen"}})
        self.assertEqual(self._anzahl_profile(), vorher)


if __name__ == "__main__":
    unittest.main()
