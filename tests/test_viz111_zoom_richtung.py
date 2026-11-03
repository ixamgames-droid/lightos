"""VIZ-111 (Teil 1+2): Laufrichtung des Zoom-Kanals je Profil.

Der Weg, der hier gemessen wird: Haken „Zoom-Kanal umgekehrt (0 = weit)“ im
Fixture-Editor bzw. -Generator -> Spalte ``FixtureProfile.zoom_inverted`` ->
Bibliotheksdatei (``zoom_umgekehrt``, Import/Export) -> Nutzlast des
3D-Visualizers (``zoomInverted``) -> Neuaufbau platzierter Geraete bei
Aenderung. Was die Szene daraus zeichnet, misst
``test_viz111_zoom_richtung_scene.py`` in echter QWebEngine.

Ohne Angabe bleibt alles wie vorher: das Feld fehlt in der Datei, die
Nutzlast traegt ``False`` und der Renderer nimmt „0 = eng, 255 = weit“ an.
"""
from __future__ import annotations

import json
import os
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                     # noqa: E402
from sqlalchemy import text                                    # noqa: E402
from sqlalchemy.orm import Session                             # noqa: E402

from src.core import abstrahlwinkel as AW                      # noqa: E402
from src.core.database import bibliothek_format as BF          # noqa: E402
from src.core.database.models import (                         # noqa: E402
    FixtureProfile, PatchedFixture, migrate_fixtures_db)
from src.ui.widgets import fixture_editor as editor_module     # noqa: E402
from src.ui.widgets import fixture_generator as gen_module     # noqa: E402
from src.ui.widgets.abstrahlwinkel_feld import (               # noqa: E402
    ZOOM_UMGEKEHRT_TEXT)
from test_fm64_abstrahlwinkel import (                         # noqa: E402
    _DbFall, _datei, _dict_for)

_app = QApplication.instance() or QApplication([])

import pytest as _pytest                                       # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets        # noqa: E402


@_pytest.fixture(autouse=True)
def _keine_widget_reste():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _umgekehrt(engine, pid) -> bool:
    with Session(engine) as s:
        return bool(s.get(FixtureProfile, pid).zoom_inverted)


class RegelnTest(unittest.TestCase):

    def test_aus_daten_nur_echtes_true(self):
        self.assertTrue(AW.zoom_umgekehrt_aus_daten(True))
        for w in (None, False, 1, "true", "ja"):
            self.assertFalse(AW.zoom_umgekehrt_aus_daten(w), w)

    def test_aus_profil_ohne_spalte_normal(self):
        self.assertFalse(AW.zoom_umgekehrt_aus_profil(SimpleNamespace()))
        self.assertTrue(AW.zoom_umgekehrt_aus_profil(
            SimpleNamespace(zoom_inverted=True)))


class MigrationTest(unittest.TestCase):

    def test_alte_fixtures_db_bekommt_die_spalte(self):
        from sqlalchemy import create_engine
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        eng = create_engine(f"sqlite:///{path}")
        self.addCleanup(eng.dispose)
        with eng.begin() as c:
            c.execute(text("CREATE TABLE fixtures (id INTEGER PRIMARY KEY, "
                           "name VARCHAR(120))"))
        migrate_fixtures_db(eng)
        with eng.begin() as c:
            cols = {r[1] for r in c.execute(text("PRAGMA table_info(fixtures)"))}
        self.assertIn("zoom_inverted", cols)


class BibliothekTest(_DbFall):

    def _import_export(self, daten):
        tmp = tempfile.mkdtemp()
        datei = os.path.join(tmp, "p.json")
        with open(datei, "w", encoding="utf-8") as fh:
            json.dump(daten, fh)
        pid = BF.importiere(datei, engine=self.engine)
        return pid, BF.exportiere(pid, engine=self.engine)

    def test_pruefung(self):
        self.assertEqual(BF.pruefe(_datei(zoom_umgekehrt=True)), [])
        self.assertEqual(BF.pruefe(_datei(zoom_umgekehrt=False)), [])
        befunde = BF.pruefe(_datei(zoom_umgekehrt="ja"))
        self.assertTrue(any("zoom_umgekehrt" in b for b in befunde), befunde)

    def test_import_export_umgekehrt(self):
        pid, raus = self._import_export(
            _datei(abstrahlwinkel=[8, 40], zoom_umgekehrt=True))
        self.assertTrue(_umgekehrt(self.engine, pid))
        self.assertIs(raus.get("zoom_umgekehrt"), True)
        self.assertEqual(BF.pruefe(raus), [])

    def test_ohne_angabe_bleibt_das_feld_weg(self):
        pid, raus = self._import_export(_datei())
        self.assertFalse(_umgekehrt(self.engine, pid))
        self.assertNotIn("zoom_umgekehrt", raus)

    def test_geaenderte_laufrichtung_ist_eine_aenderung(self):
        with Session(self.engine) as s:
            p = FixtureProfile(name="X", short_name="X", fixture_type="par")
            vorher = BF._vergleichsform(p)
            p.zoom_inverted = True
            self.assertNotEqual(vorher, BF._vergleichsform(p))


class GeneratorTest(_DbFall):

    def setUp(self):
        super().setUp()
        for methode in ("information", "warning", "question"):
            pm = mock.patch.object(gen_module.QMessageBox, methode)
            m = pm.start()
            self.addCleanup(pm.stop)
            if methode == "question":
                m.return_value = gen_module.QMessageBox.StandardButton.Yes

    def test_payload_und_speichern(self):
        model = gen_module.GeneratorModel(
            model="Zoom Gen", short_name="ZGEN111", zoom_umgekehrt=True,
            modes=[gen_module.GenMode("Default", gen_module.beispiel_kanaele())])
        payload = gen_module.build_profile_payload(model)
        self.assertIs(payload["zoom_inverted"], True)
        pid = gen_module.save_generated_profile(payload, engine=self.engine)
        self.assertTrue(_umgekehrt(self.engine, pid))

    def test_ohne_angabe_normal(self):
        model = gen_module.GeneratorModel(
            model="Zoom Gen0", short_name="ZGEN0",
            modes=[gen_module.GenMode("Default", gen_module.beispiel_kanaele())])
        pid = gen_module.save_generated_profile(
            gen_module.build_profile_payload(model), engine=self.engine)
        self.assertFalse(_umgekehrt(self.engine, pid))

    def test_vorlage_traegt_die_richtung_in_den_dialog(self):
        model = gen_module.model_from_daten(_datei(zoom_umgekehrt=True))
        self.assertTrue(model.zoom_umgekehrt)
        dlg = gen_module.FixtureGeneratorDialog(model=model)
        self.addCleanup(dlg.deleteLater)
        cb = dlg._abstrahlwinkel.cb_zoom_umgekehrt
        self.assertTrue(cb.isChecked())
        self.assertEqual(cb.text(), ZOOM_UMGEKEHRT_TEXT)
        self.assertIn("0 = weit", cb.toolTip())
        cb.setChecked(False)
        dlg._sync_all()
        self.assertFalse(dlg._model.zoom_umgekehrt)


class EditorTest(_DbFall):

    def setUp(self):
        super().setUp()
        p = mock.patch.object(editor_module, "engine", lambda: self.engine)
        p.start()
        self.addCleanup(p.stop)
        for methode in ("information", "warning", "question"):
            pm = mock.patch.object(editor_module.QMessageBox, methode)
            m = pm.start()
            self.addCleanup(pm.stop)
            if methode == "question":
                m.return_value = editor_module.QMessageBox.StandardButton.Yes

    def test_editor_speichert_laedt_und_aendert(self):
        dlg = editor_module.FixtureEditorDialog()
        self.addCleanup(dlg.deleteLater)
        dlg._cb_manufacturer.setEditText("Eigenbau VIZ111")
        dlg._edit_name.setText("Editor Zoom")
        dlg._edit_short.setText("EDZ111")
        dlg._tabs.currentWidget()._add_channel()
        dlg._abstrahlwinkel.cb_zoom_umgekehrt.setChecked(True)
        dlg._save()
        pid = dlg.saved_id
        self.assertIsNotNone(pid, "Editor hat nicht gespeichert")
        self.assertTrue(_umgekehrt(self.engine, pid))
        dlg2 = editor_module.FixtureEditorDialog(fixture_id=pid)
        self.addCleanup(dlg2.deleteLater)
        self.assertTrue(dlg2._abstrahlwinkel.zoom_umgekehrt())
        self.assertIs(dlg2._lightos_daten().get("zoom_umgekehrt"), True)
        dlg2._abstrahlwinkel.setze_zoom_umgekehrt(False)
        dlg2._save()
        self.assertFalse(_umgekehrt(self.engine, pid))


class NutzlastTest(_DbFall):

    def _profil(self, umgekehrt, short_name):
        model = gen_module.GeneratorModel(
            model="Nutzlast " + short_name, short_name=short_name,
            zoom_umgekehrt=umgekehrt,
            modes=[gen_module.GenMode("Default", gen_module.beispiel_kanaele())])
        return gen_module.save_generated_profile(
            gen_module.build_profile_payload(model), engine=self.engine)

    def _patched(self, pid):
        return PatchedFixture(fid=7, label="P", fixture_profile_id=pid,
                              mode_name="Default", universe=1, address=1,
                              channel_count=3, fixture_type="par")

    def test_umkehr_kommt_in_der_nutzlast_an(self):
        d = _dict_for(self._patched(self._profil(True, "NUTZ111")))
        self.assertIs(d["zoomInverted"], True)

    def test_gegenprobe_ohne_angabe_false(self):
        d = _dict_for(self._patched(self._profil(False, "NUTZ0")))
        self.assertIs(d["zoomInverted"], False)

    def test_geaenderte_richtung_baut_platziertes_geraet_neu(self):
        from unittest.mock import MagicMock
        from src.core.app_state import clear_channel_cache
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        pid = self._profil(False, "NEU111")
        f = self._patched(pid)
        fake = SimpleNamespace(
            _state=SimpleNamespace(get_patched_fixtures=lambda: [f],
                                   visualizer_positions={7: (0, 4, 0)},
                                   visualizer_rotations={}, visualizer_docks={}),
            fixtureAdded=MagicMock())
        fake._viz_model_for = types.MethodType(
            VisualizerBridge._viz_model_for, fake)
        fake._fixture_to_dict = types.MethodType(
            VisualizerBridge._fixture_to_dict, fake)
        VisualizerBridge._fixture_to_dict(fake, f)          # ans 3D gesendet
        VisualizerBridge._nullpunkte_nachziehen(fake)       # nichts geaendert
        fake.fixtureAdded.emit.assert_not_called()
        with Session(self.engine) as s:                     # Editor speichert
            s.get(FixtureProfile, pid).zoom_inverted = True
            s.commit()
        clear_channel_cache()                               # profil_geaendert
        VisualizerBridge._nullpunkte_nachziehen(fake)
        self.assertEqual(fake.fixtureAdded.emit.call_count, 1)
        d = json.loads(fake.fixtureAdded.emit.call_args.args[0])
        self.assertIs(d["zoomInverted"], True)
        VisualizerBridge._nullpunkte_nachziehen(fake)       # nichts Neues
        self.assertEqual(fake.fixtureAdded.emit.call_count, 1)


if __name__ == "__main__":
    unittest.main()
