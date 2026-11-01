"""FM-71: die restlichen Huerden des Fixture Generators aus dem DOC-65-Durchlauf.

1. Spalten „Name“ und „Attribut“ schnitten ab („Position X (0-1…“,
   „fect_speed“, „lor_change“).
2. Hinweise (z. B. „Laser-Sicherheit“) kamen erst nach „Prüfen“, nicht beim
   Eintippen.
3. Nach „Speichern“ eine modale Erfolgsmeldung.
4. Ein neuer Generator startete mit vier RGB-Beispielkanaelen.
5. Ein gespeichertes Profil liess sich im Generator nicht wieder oeffnen.

Alles laeuft in einer Wegwerf-Fixture-DB (``FDB._engine`` ersetzt);
Meldungen und Auswahldialoge sind ersetzt. Kein DMX, keine echte Bibliothek.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                   # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402
from PySide6.QtWidgets import (QApplication, QMainWindow,       # noqa: E402
                               QPushButton)
from sqlalchemy.orm import Session                              # noqa: E402

from src.core.database import bibliothek_format as BF           # noqa: E402
from src.core.database import fixture_db as FDB                 # noqa: E402
from src.core.database.fixture_db import get_engine             # noqa: E402
from src.core.database.models import (                          # noqa: E402
    FixtureProfile, create_all_idempotent)
from src.ui.widgets import fixture_generator as FG              # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                                # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets         # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AURO = os.path.join(_REPO, "fixtures", "bibliothek", "cameo", "auro-spot-100.json")

#: Wartezeit fuer die entprellte Hinweisliste (deutlich ueber der Verzoegerung).
_WARTEN_MS = getattr(FG, "HINWEIS_VERZOEGERUNG_MS", 400) + 600


class _Fall(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fm71_")
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

    def _dialog(self, model=None, *, zeigen=False):
        dlg = FG.FixtureGeneratorDialog(model=model)
        self.addCleanup(dlg.deleteLater)
        if zeigen:
            dlg.resize(1200, 900)
            dlg.show()
            _app.processEvents()
        return dlg

    def _profil_anlegen(self, *, hersteller, modell, short_name, source="user",
                        kanaele=(("Dimmer", "intensity"),), herkunft=None) -> int:
        model = FG.GeneratorModel(
            manufacturer=hersteller, model=modell, short_name=short_name,
            fixture_type="par",
            modes=[FG.GenMode("2-Kanal", [FG.GenChannel(n, a) for n, a in kanaele])])
        payload = model.to_payload()
        payload["source"] = source
        return FDB.create_user_profile(payload, engine=self.engine,
                                       herkunft=herkunft)

    def _anzahl_profile(self) -> int:
        with Session(self.engine) as s:
            return s.query(FixtureProfile).count()


# ── (1) Spaltenbreite ─────────────────────────────────────────────────────────

class SpaltenLesbarTest(_Fall):

    _KANAELE = (("Position X (0-10 = Mitte)", "laser_x"),
                ("Effekt-Tempo", "effect_speed"),
                ("Farbwechsel", "laser_color_change"))

    def _tab(self):
        model = FG.GeneratorModel(
            manufacturer="Eigenbau", model="FM71 Spalten", short_name="FM71SP",
            fixture_type="laser",
            modes=[FG.GenMode("3-Kanal", [FG.GenChannel(n, a)
                                          for n, a in self._KANAELE])])
        dlg = self._dialog(model, zeigen=True)
        return dlg._tabs.currentWidget()

    def test_name_passt_in_die_spalte(self):
        tab = self._tab()
        tbl = tab._tbl
        fm = tbl.fontMetrics()
        for row, (name, _a) in enumerate(self._KANAELE):
            self.assertGreaterEqual(
                tbl.columnWidth(1), fm.horizontalAdvance(name),
                f"Spalte „Name“ zu schmal fuer „{name}“ — wird abgeschnitten.")
            self.assertEqual(tbl.item(row, 1).toolTip(), name)

    def test_attribut_passt_in_das_auswahlfeld(self):
        tab = self._tab()
        tbl = tab._tbl
        for row, (_n, attr) in enumerate(self._KANAELE):
            cb = tbl.cellWidget(row, 2)
            self.assertEqual(cb.currentText(), attr)
            platz = cb.lineEdit().width()
            self.assertGreaterEqual(
                platz, cb.lineEdit().fontMetrics().horizontalAdvance(attr),
                f"Attribut „{attr}“ passt nicht ins Feld ({platz} px) — "
                "es zeigt nur das Ende des Worts.")
            self.assertEqual(cb.toolTip(), attr)


# ── (2) Hinweise live ─────────────────────────────────────────────────────────

class HinweiseLiveTest(_Fall):

    def test_ueberlappung_erscheint_beim_eintippen(self):
        kanal = FG.GenChannel("Shutter", "shutter", 255, 255, ranges=[
            FG.GenRange(0, 10, "Zu", "closed"),
            FG.GenRange(11, 255, "Auf", "open")])
        model = FG.GeneratorModel(manufacturer="Eigenbau", model="FM71 Live",
                                  short_name="FM71LV",
                                  modes=[FG.GenMode("1-Kanal", [kanal])])
        dlg = self._dialog(model, zeigen=True)
        self.assertNotIn("überlappen", dlg._issues.toPlainText())
        bereiche = dlg._tabs.currentWidget()._range_editor
        bereiche._tbl.item(1, 0).setText("5")      # „Auf“ ab 5 statt 11
        QTest.qWait(_WARTEN_MS)
        self.assertIn("überlappen", dlg._issues.toPlainText(),
                      "Hinweisliste blieb stehen — erst „Prüfen“ zeigt sie.")

    def test_laser_sicherheit_erscheint_beim_waehlen_der_art(self):
        """Der DOC-65-Fall: die Art „closed“ am Betriebsart-Kanal waehlen."""
        kanal = FG.GenChannel("Betriebsart", "shutter", 0, 255, ranges=[
            FG.GenRange(0, 49, "Modus A", ""),
            FG.GenRange(50, 255, "Auto", "open")])
        model = FG.GeneratorModel(manufacturer="Eigenbau", model="FM71 Laser",
                                  short_name="FM71LS", fixture_type="laser",
                                  modes=[FG.GenMode("1-Kanal", [kanal])])
        dlg = self._dialog(model, zeigen=True)
        self.assertNotIn("Laser-Sicherheit", dlg._issues.toPlainText())
        bereiche = dlg._tabs.currentWidget()._range_editor
        bereiche._tbl.cellWidget(0, 3).setCurrentText("closed")
        QTest.qWait(_WARTEN_MS)
        self.assertIn("Laser-Sicherheit", dlg._issues.toPlainText())

    def test_entprellt(self):
        """Nicht bei jedem Tastendruck rechnen: unmittelbar nach der Eingabe
        steht die alte Liste noch, erst nach der Verzoegerung die neue."""
        dlg = self._dialog(zeigen=True)
        tab = dlg._tabs.currentWidget()
        tab.beispiel_einfuegen()
        _app.processEvents()
        self.assertIn("keine Kanäle", dlg._issues.toPlainText())
        QTest.qWait(_WARTEN_MS)
        self.assertNotIn("keine Kanäle", dlg._issues.toPlainText())


# ── (3) keine modale Erfolgsmeldung ──────────────────────────────────────────

class SpeichernOhneBoxTest(_Fall):

    def test_speichern_ohne_modale_meldung(self):
        model = FG.GeneratorModel(
            manufacturer="Eigenbau", model="FM71 Speichern", short_name="FM71SV",
            modes=[FG.GenMode("1-Kanal", [FG.GenChannel("Dimmer", "intensity")])])
        dlg = self._dialog(model)
        dlg._save()
        self.assertIsNotNone(dlg.saved_id)
        self.assertEqual(self.meldung["warning"].call_args_list, [])
        self.assertEqual(self.meldung["information"].call_args_list, [],
                         "Nach dem Speichern kam eine modale Meldungsbox.")
        self.assertIn("FM71 Speichern", getattr(dlg, "gespeichert_meldung", ""))

    def test_patch_ansicht_zeigt_die_meldung_in_der_statuszeile(self):
        from src.ui.views.patch_view import PatchView

        class _Attrappe:
            saved_id = 7
            gespeichert_meldung = "Fixture-Profil „X“ gespeichert."

            def __init__(self, _parent):
                pass

            def exec(self):
                return 1

        fenster = QMainWindow()
        self.addCleanup(fenster.deleteLater)
        selbst = types.SimpleNamespace(window=lambda: fenster,
                                       _refresh_table=mock.Mock())
        with mock.patch.object(FG, "FixtureGeneratorDialog", _Attrappe):
            PatchView._open_generator(selbst)
        selbst._refresh_table.assert_called_once()
        self.assertEqual(fenster.statusBar().currentMessage(),
                         _Attrappe.gespeichert_meldung)


# ── (4) leer starten ──────────────────────────────────────────────────────────

class LeerStartenTest(_Fall):

    def test_neuer_generator_hat_keine_kanaele(self):
        dlg = self._dialog()
        self.assertEqual(len(dlg._model.modes), 1)
        self.assertEqual(dlg._model.modes[0].channels, [],
                         "Neuer Generator startet mit Beispielkanaelen.")
        self.assertEqual(dlg._tabs.currentWidget()._tbl.rowCount(), 0)

    def test_beispiel_einfuegen_auf_knopfdruck(self):
        dlg = self._dialog(zeigen=True)
        knopf = next((b for b in dlg.findChildren(QPushButton)
                      if b.text() == "Beispiel einfügen"), None)
        self.assertIsNotNone(knopf, "Kein Knopf „Beispiel einfügen“")
        QTest.mouseClick(knopf, Qt.MouseButton.LeftButton,
                         pos=knopf.rect().center())
        _app.processEvents()
        mode = dlg._model.modes[0]
        self.assertEqual([c.attribute for c in mode.channels],
                         ["intensity", "color_r", "color_g", "color_b"])
        self.assertEqual(dlg._tabs.currentWidget()._tbl.rowCount(), 4)


# ── (5) eigenes Profil wieder oeffnen ─────────────────────────────────────────

class EigenesProfilOeffnenTest(_Fall):

    def test_liste_nennt_nur_eigene_profile(self):
        eigen = self._profil_anlegen(hersteller="Eigenbau", modell="FM71 Eigen",
                                     short_name="FM71E")
        self._profil_anlegen(hersteller="Eigenbau", modell="FM71 Mitgeliefert",
                             short_name="FM71M", source="builtin")
        self._profil_anlegen(hersteller="Eigenbau", modell="FM71 Import",
                             short_name="FM71Q", source="qlcplus")
        self.assertEqual(FG.eigene_profile(self.engine),
                         [(eigen, "Eigenbau — FM71 Eigen")])

    def test_oeffnen_laedt_das_profil_und_speichert_neu(self):
        pid = self._profil_anlegen(
            hersteller="Eigenbau", modell="FM71 Wieder", short_name="FM71W",
            kanaele=(("Dimmer", "intensity"), ("Strobe", "strobe")))
        dlg = self._dialog()
        with mock.patch.object(FG.QInputDialog, "getItem",
                               return_value=("Eigenbau — FM71 Wieder", True)):
            dlg._eigenes_profil_oeffnen()
        self.assertEqual(self.meldung["warning"].call_args_list, [])
        self.assertEqual((dlg._edit_mfr.text(), dlg._edit_model.text()),
                         ("Eigenbau", "FM71 Wieder"))
        self.assertEqual([c.name for c in dlg._model.modes[0].channels],
                         ["Dimmer", "Strobe"])
        self.assertEqual(dlg._model.herkunft_fehlt, "")
        vorher = self._anzahl_profile()
        dlg._save()
        self.assertIsNotNone(dlg.saved_id)
        self.assertNotEqual(dlg.saved_id, pid)
        self.assertEqual(self._anzahl_profile(), vorher + 1)

    def test_herkunft_eines_eigenen_profils_aus_vorlage_reist_mit(self):
        """FM-76/UI-82: ein eigenes Profil, das aus einer QLC+-Vorlage gebaut
        wurde, behaelt beim erneuten Oeffnen und Speichern deren Lizenz."""
        vorlage = BF.lade_datei(_AURO)
        herkunft = {k: vorlage[k] for k in BF.HERKUNFT_SCHLUESSEL}
        self._profil_anlegen(hersteller="Eigenbau", modell="FM71 Auro",
                             short_name="FM71A", herkunft=herkunft)
        dlg = self._dialog()
        with mock.patch.object(FG.QInputDialog, "getItem",
                               return_value=("Eigenbau — FM71 Auro", True)):
            dlg._eigenes_profil_oeffnen()
        dlg._save()
        with Session(self.engine) as s:
            h = BF.herkunft_fuer(s.get(FixtureProfile, dlg.saved_id))
        self.assertEqual((h["herkunft"]["art"], h["herkunft"]["lizenz"]),
                         ("qlcplus", "Apache-2.0"))

    def test_gleichnamige_eigene_profile_bleiben_waehlbar(self):
        """Oeffnen → Speichern legt ein NEUES gleichnamiges Profil an; die
        Auswahlliste liefert nur Text — beide muessen unterscheidbar sein,
        sonst oeffnet die Wahl immer das erste."""
        erst = self._profil_anlegen(hersteller="Eigenbau", modell="FM71 Doppelt",
                                    short_name="FM71D1")
        zweit = self._profil_anlegen(
            hersteller="Eigenbau", modell="FM71 Doppelt", short_name="FM71D2",
            kanaele=(("Dimmer", "intensity"), ("Strobe", "strobe")))
        liste = FG.eigene_profile(self.engine)
        texte = [t for _p, t in liste]
        self.assertEqual(len(set(texte)), 2, f"Doppelte Eintraege: {texte}")
        zweit_text = dict(liste)[zweit]
        dlg = self._dialog()
        with mock.patch.object(FG.QInputDialog, "getItem",
                               return_value=(zweit_text, True)):
            dlg._eigenes_profil_oeffnen()
        self.assertEqual([c.name for c in dlg._model.modes[0].channels],
                         ["Dimmer", "Strobe"])
        self.assertNotEqual(erst, zweit)

    def test_ohne_eigene_profile_kommt_ein_hinweis(self):
        dlg = self._dialog()
        with mock.patch.object(FG.QInputDialog, "getItem") as wahl:
            dlg._eigenes_profil_oeffnen()
        wahl.assert_not_called()
        self.meldung["information"].assert_called_once()


if __name__ == "__main__":
    unittest.main()
