"""FM-71 (Rest): „Profil aktualisieren“ im Fixture Generator.

Nach „Eigenes Profil öffnen…“ gab es keinen Weg, das geoeffnete Profil zu
UEBERSCHREIBEN — „Speichern“ legt immer ein neues an. Jetzt:

* der Knopf ist nur aktiv, wenn ein eigenes Profil geoeffnet ist (jede andere
  Vorlage schaltet ihn wieder aus);
* er ueberschreibt genau diese Profil-ID — mit Rueckfrage (Vorauswahl Nein);
* mitgelieferte und importierte Profile sind geschuetzt (auch in
  ``fixture_db.update_user_profile`` selbst);
* gepatchte Geraete: dieselben Folgen-Zeilen wie im Fixture-Editor (UI-74) in
  der Rueckfrage, danach ``profil_geaendert`` (UI-81);
* kein neues Hersteller+Modell-Duplikat (Riegel wie im Editor).

Alles in einer frisch geseedeten Wegwerf-Bibliothek (``frische_library``);
Meldungen sind ersetzt. Kein DMX, keine echten Daten.
"""
from __future__ import annotations

import os
import time
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest                                # noqa: E402
from PySide6.QtWidgets import QApplication                      # noqa: E402
from sqlalchemy import select                                   # noqa: E402
from sqlalchemy.orm import Session                              # noqa: E402

from src.core.database import fixture_db as FDB                 # noqa: E402
from src.core.database.models import (                          # noqa: E402
    FixtureChannel, FixtureMode, FixtureProfile)
from src.ui import touch_keyboard as tk                         # noqa: E402
from src.ui import ziehen_scrollen as zs                        # noqa: E402
from src.ui.widgets import fixture_generator as FG              # noqa: E402

from _fixture_quelle import frische_library                     # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets         # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

JA = FG.QMessageBox.StandardButton.Yes
NEIN = FG.QMessageBox.StandardButton.No


def _warte_bis(bedingung, s: float = 5.0) -> bool:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


class _Fall(unittest.TestCase):

    def setUp(self):
        self.engine = frische_library(self)
        self.addCleanup(destroy_all_top_level_widgets, _app)
        self.meldung = {}
        for methode in ("information", "warning", "question"):
            pm = mock.patch.object(FG.QMessageBox, methode)
            self.meldung[methode] = pm.start()
            self.addCleanup(pm.stop)
        self.meldung["question"].return_value = JA
        # Keine Show, keine gepatchten Geraete — einzelne Tests ersetzen das.
        pg = mock.patch("src.ui.widgets.fixture_editor._gepatchte_geraete",
                        return_value=[])
        self.gepatcht = pg.start()
        self.addCleanup(pg.stop)
        pa = mock.patch("src.core.app_state.profil_geaendert")
        self.profil_geaendert = pa.start()
        self.addCleanup(pa.stop)

    # ── Helfer ──────────────────────────────────────────────────────────
    def _eigenes(self, modell="FM71 Eigen", kanaele=("Dimmer", "Rot")) -> int:
        model = FG.GeneratorModel(
            manufacturer="Eigenbau", model=modell, short_name="FM71",
            modes=[FG.GenMode("Standard", [
                FG.GenChannel(n, "intensity" if i == 0 else "color_r", 0, 255)
                for i, n in enumerate(kanaele)])])
        return FG.save_generated_profile(model.to_payload(), engine=self.engine)

    def _dialog(self, *, zeigen=False):
        dlg = FG.FixtureGeneratorDialog()
        self.addCleanup(dlg.deleteLater)
        if zeigen:
            dlg.resize(1200, 900)
            dlg.show()
            _warte_bis(dlg.isVisible)
        return dlg

    def _oeffnen(self, dlg, pid):
        text = dict(FG.eigene_profile(self.engine))[pid]
        with mock.patch.object(FG.QInputDialog, "getItem",
                               return_value=(text, True)):
            dlg._eigenes_profil_oeffnen()
        self.assertEqual(dlg._geoeffnet_id, pid)

    def _kanaele(self, pid) -> list[str]:
        with Session(self.engine) as s:
            mode = s.execute(select(FixtureMode).where(
                FixtureMode.fixture_id == pid)).scalars().first()
            return [c.name for c in s.execute(
                select(FixtureChannel).where(FixtureChannel.mode_id == mode.id)
                .order_by(FixtureChannel.channel_number)).scalars()]

    def _anzahl(self) -> int:
        with Session(self.engine) as s:
            return len(s.execute(select(FixtureProfile.id)).all())

    def _builtin(self) -> int:
        with Session(self.engine) as s:
            return s.execute(select(FixtureProfile.id).where(
                FixtureProfile.source != "user")).scalars().first()


# ── Knopf-Zustand ─────────────────────────────────────────────────────────

class KnopfZustand(_Fall):

    def test_neuer_generator_knopf_aus(self):
        dlg = self._dialog()
        self.assertEqual(dlg._btn_aktualisieren.text(), "Profil aktualisieren")
        self.assertFalse(dlg._btn_aktualisieren.isEnabled())
        self.assertIn("Eigenes Profil öffnen", dlg._btn_aktualisieren.toolTip())

    def test_nach_oeffnen_an_andere_vorlage_wieder_aus(self):
        pid = self._eigenes()
        dlg = self._dialog()
        self._oeffnen(dlg, pid)
        self.assertTrue(dlg._btn_aktualisieren.isEnabled())
        self.assertIn(f"Nr. {pid}", dlg._btn_aktualisieren.toolTip())
        # Eine andere Vorlage (Import, .json) darf das Profil nie still
        # ueberschreiben.
        dlg.set_model(FG.GeneratorModel(manufacturer="X", model="Y"))
        self.assertIsNone(dlg._geoeffnet_id)
        self.assertFalse(dlg._btn_aktualisieren.isEnabled())

    def test_return_loest_aktualisieren_nicht_aus(self):
        pid = self._eigenes()
        dlg = self._dialog(zeigen=True)
        self._oeffnen(dlg, pid)
        self.assertFalse(dlg._btn_aktualisieren.autoDefault())
        with mock.patch.object(FDB, "update_user_profile") as upd:
            QTest.keyClick(dlg._edit_model, FG.Qt.Key.Key_Return)
            QApplication.processEvents()
        upd.assert_not_called()


# ── Ueberschreiben ────────────────────────────────────────────────────────

class Ueberschreiben(_Fall):

    def test_ueberschreibt_genau_diese_id(self):
        pid = self._eigenes()
        anderes = self._eigenes("FM71 Anderes")
        vorher = self._anzahl()
        dlg = self._dialog()
        self._oeffnen(dlg, pid)
        dlg._model.modes[0].channels.append(
            FG.GenChannel("Blau", "color_b", 0, 255))
        dlg._reload_modes()
        dlg._aktualisieren()
        self.assertEqual(self._anzahl(), vorher)          # kein neues Profil
        self.assertEqual(self._kanaele(pid), ["Dimmer", "Rot", "Blau"])
        self.assertEqual(self._kanaele(anderes), ["Dimmer", "Rot"])
        self.assertEqual(dlg.saved_id, pid)
        self.assertIn("aktualisiert", dlg.gespeichert_meldung)
        self.profil_geaendert.assert_called_once_with(pid)
        with Session(self.engine) as s:
            self.assertEqual(s.get(FixtureProfile, pid).source, "user")
        # Rueckfrage mit Vorauswahl „Nein“, nennt die Profilnummer.
        args = self.meldung["question"].call_args.args
        self.assertIn(f"Nr. {pid}", args[2])
        self.assertEqual(args[4], NEIN)

    def test_nein_aendert_nichts(self):
        pid = self._eigenes()
        dlg = self._dialog()
        self._oeffnen(dlg, pid)
        dlg._model.modes[0].channels.pop()
        dlg._reload_modes()
        self.meldung["question"].return_value = NEIN
        dlg._aktualisieren()
        self.assertEqual(self._kanaele(pid), ["Dimmer", "Rot"])
        self.assertIsNone(dlg.saved_id)
        self.profil_geaendert.assert_not_called()

    def test_herkunft_bleibt(self):
        pid = self._eigenes()
        with Session(self.engine) as s:
            p = s.get(FixtureProfile, pid)
            p.herkunft, p.provenance = '{"x": 1}', "prov"
            s.commit()
        dlg = self._dialog()
        self._oeffnen(dlg, pid)
        dlg._aktualisieren()
        with Session(self.engine) as s:
            p = s.get(FixtureProfile, pid)
            self.assertEqual((p.herkunft, p.provenance), ('{"x": 1}', "prov"))

    def test_umbenennen_auf_vorhandenes_modell_abgelehnt(self):
        pid = self._eigenes()
        self._eigenes("FM71 Belegt")
        dlg = self._dialog()
        self._oeffnen(dlg, pid)
        dlg._edit_model.setText("fm71  belegt")
        dlg._aktualisieren()
        self.meldung["warning"].assert_called()
        self.assertIn("steht schon", self.meldung["warning"].call_args.args[2])
        with Session(self.engine) as s:
            self.assertEqual(s.get(FixtureProfile, pid).name, "FM71 Eigen")

    def test_gleichnamige_geschwister_blockieren_nicht(self):
        """Altes „öffnen → speichern“ hinterliess gleichnamige eigene Profile —
        ohne Umbenennen bleibt jedes aktualisierbar (wie im Editor)."""
        pid = self._eigenes()
        self._eigenes()                                    # gleicher Name
        dlg = self._dialog()
        self._oeffnen(dlg, pid)
        dlg._model.modes[0].channels.pop()
        dlg._reload_modes()
        dlg._aktualisieren()
        self.meldung["warning"].assert_not_called()
        self.assertEqual(self._kanaele(pid), ["Dimmer"])


# ── Schutz ────────────────────────────────────────────────────────────────

class Schutz(_Fall):

    def test_kern_lehnt_builtin_ab(self):
        bid = self._builtin()
        payload = FG.GeneratorModel(manufacturer="A", model="B").to_payload()
        with self.assertRaises(FDB.ProfilGeschuetzt):
            FDB.update_user_profile(bid, payload, engine=self.engine)

    def test_kern_lehnt_import_ab(self):
        pid = self._eigenes()
        with Session(self.engine) as s:
            s.get(FixtureProfile, pid).source = "qlcplus"
            s.commit()
        payload = FG.GeneratorModel(manufacturer="A", model="B").to_payload()
        with self.assertRaises(FDB.ProfilGeschuetzt):
            FDB.update_user_profile(pid, payload, engine=self.engine)
        self.assertEqual(self._kanaele(pid), ["Dimmer", "Rot"])

    def test_dialog_schaltet_bei_fremder_quelle_ab(self):
        """Wird das geoeffnete Profil inzwischen etwas anderes (oder steht
        eine fremde ID im Dialog), schreibt der Knopf nichts."""
        pid = self._eigenes()
        dlg = self._dialog()
        self._oeffnen(dlg, pid)
        with Session(self.engine) as s:
            s.get(FixtureProfile, pid).source = "builtin"
            s.commit()
        dlg._model.modes[0].channels.pop()
        dlg._reload_modes()
        dlg._aktualisieren()
        self.assertEqual(self._kanaele(pid), ["Dimmer", "Rot"])
        self.assertIn("kein eigenes Profil",
                      self.meldung["warning"].call_args.args[2])
        self.assertFalse(dlg._btn_aktualisieren.isEnabled())

    def test_eigene_profile_bietet_kein_builtin_an(self):
        bid = self._builtin()
        self.assertNotIn(bid, dict(FG.eigene_profile(self.engine)))


# ── Gepatchte Geraete ─────────────────────────────────────────────────────

class Gepatcht(_Fall):

    def test_rueckfrage_nennt_folgen_wie_editor(self):
        pid = self._eigenes()
        self.gepatcht.return_value = [types.SimpleNamespace(
            fixture_profile_id=pid, mode_name="Standard", channel_count=2,
            label="Front links", fid=1)]
        dlg = self._dialog()
        self._oeffnen(dlg, pid)
        dlg._model.modes[0].channels.append(
            FG.GenChannel("Blau", "color_b", 0, 255))
        dlg._reload_modes()
        self.meldung["question"].return_value = NEIN
        dlg._aktualisieren()
        text = self.meldung["question"].call_args.args[2]
        self.assertIn("gepatcht", text)
        self.assertIn("Front links", text)
        self.assertIn("3 statt 2", text)
        self.assertEqual(self._kanaele(pid), ["Dimmer", "Rot"])

    def test_ja_baut_patch_neu(self):
        pid = self._eigenes()
        self.gepatcht.return_value = [types.SimpleNamespace(
            fixture_profile_id=pid, mode_name="Standard", channel_count=2,
            label="Front links", fid=1)]
        dlg = self._dialog()
        self._oeffnen(dlg, pid)
        dlg._aktualisieren()
        self.profil_geaendert.assert_called_once_with(pid)


# ── Alte Profile (vor FM-71 angelegt) ─────────────────────────────────────

class AltesProfil(_Fall):

    def test_alt_angelegtes_profil_ohne_neue_felder(self):
        """Ein eigenes Profil wie aus aelteren Staenden: Payload ohne
        Raster-, Segment- und Laser-Schluessel (Handbau)."""
        pid = FDB.create_user_profile({
            "manufacturer": "Altbau", "name": "Alt FM71",
            "modes": [{"name": "Std", "channels": [
                {"name": "Dim", "attribute": "intensity"}]}]},
            engine=self.engine)
        dlg = self._dialog()
        self._oeffnen(dlg, pid)
        dlg._model.modes[0].channels.append(
            FG.GenChannel("Strobe", "shutter", 0, 255))
        dlg._reload_modes()
        dlg._aktualisieren()
        self.assertEqual(self._kanaele(pid), ["Dim", "Strobe"])


# ── Finger und Touch-Groesse ──────────────────────────────────────────────

class Finger(_Fall):

    def setUp(self):
        super().setUp()
        vorher = tk.is_touch_mode()
        tk.setze_touch_modus(True)
        self.addCleanup(tk.setze_touch_modus, vorher)
        # Der Anwendungsfilter (UI-110), der im Programm Finger in Klicks
        # uebersetzt — wie in tests/test_ui116_mehrfach_touch.py.
        filt = zs.einrichten(_app)
        alt = filt.aktiv
        filt.aktiv = True
        self.addCleanup(setattr, filt, "aktiv", alt)

    def test_tipp_ueberschreibt_und_knopf_gross_genug(self):
        pid = self._eigenes()
        dlg = self._dialog()
        # Wie das Hauptfenster im Touch-Modus (main_window: QPushButton-Regel).
        dlg.setStyleSheet("QPushButton { min-height: 38px; padding: 6px 14px; "
                          "font-size: 14px; }\n" + tk.touch_qss())
        dlg.show()
        # Ganz auf dem (Offscreen-)Bildschirm, sonst kommt der Finger nicht an.
        bild = dlg.screen().availableGeometry()
        dlg.setGeometry(bild.x(), bild.y(), bild.width() - 20, bild.height() - 40)
        _warte_bis(lambda: dlg.isVisible() and bild.contains(
            dlg._btn_aktualisieren.mapToGlobal(
                dlg._btn_aktualisieren.rect().center())))
        self._oeffnen(dlg, pid)
        knopf = dlg._btn_aktualisieren
        self.assertTrue(_warte_bis(lambda: knopf.height() >= 44))
        self.assertGreaterEqual(knopf.width(), 44)
        dlg._model.modes[0].channels.pop()
        dlg._reload_modes()
        p = knopf.rect().center()
        QTest.touchEvent(knopf, _DEV).press(0, p, knopf).commit()
        QTest.touchEvent(knopf, _DEV).release(0, p, knopf).commit()
        self.assertTrue(_warte_bis(lambda: dlg.saved_id == pid))
        self.assertEqual(self._kanaele(pid), ["Dimmer"])

    def test_maus_klick_wirkt_wie_vorher(self):
        pid = self._eigenes()
        tk.setze_touch_modus(False)
        dlg = self._dialog(zeigen=True)
        self._oeffnen(dlg, pid)
        QTest.mouseClick(dlg._btn_aktualisieren, FG.Qt.MouseButton.LeftButton)
        self.assertTrue(_warte_bis(lambda: dlg.saved_id == pid))


if __name__ == "__main__":
    unittest.main()
