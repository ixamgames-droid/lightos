"""FM-64 (Teil 1): Abstrahlwinkel im Fixture-Profil.

Der Weg, der hier gemessen wird: Eingabe im Fixture-Editor bzw. -Generator ->
Spalten ``FixtureProfile.beam_angle_min/_max`` -> Bibliotheksdatei
(``abstrahlwinkel``, Import/Export) -> Nutzlast des 3D-Visualizers
(``beamAngleMin``/``beamAngleMax``). Was die Szene daraus zeichnet, misst
``test_fm64_abstrahlwinkel_scene.py`` in echter QWebEngine.

Ohne Angabe bleibt alles wie vorher: das Feld fehlt in der Datei, die
Nutzlast traegt 0/0 und der Renderer leitet den Kegel aus Typ/Zoom ab.
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
from sqlalchemy import select, text                            # noqa: E402
from sqlalchemy.orm import Session                             # noqa: E402

from src.core import abstrahlwinkel as AW                      # noqa: E402
from src.core.database import bibliothek_format as BF          # noqa: E402
from src.core.database import fixture_db as FDB                # noqa: E402
from src.core.database.fixture_db import get_engine            # noqa: E402
from src.core.database.models import (                         # noqa: E402
    FixtureProfile, PatchedFixture, create_all_idempotent, migrate_fixtures_db)
from src.ui.widgets import fixture_editor as editor_module     # noqa: E402
from src.ui.widgets import fixture_generator as gen_module     # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest                                       # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets        # noqa: E402


@_pytest.fixture(autouse=True)
def _keine_widget_reste():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _dict_for(f):
    """Die ECHTE Nutzlast-Erzeugung des Visualizers."""
    from src.ui.visualizer.visualizer_window import VisualizerBridge
    fake_self = SimpleNamespace(_state=SimpleNamespace(
        visualizer_positions={}, visualizer_rotations={}, visualizer_docks={}))
    fake_self._viz_model_for = types.MethodType(
        VisualizerBridge._viz_model_for, fake_self)
    return VisualizerBridge._fixture_to_dict(fake_self, f)


def _datei(**kopf) -> dict:
    d = {
        "format_version": BF.FORMAT_VERSION, "hersteller": "Eigenbau FM64",
        "modell": "Kegel Test", "kurzname": "KEGEL64", "typ": "par",
        "quelle": {"titel": "eigenes Profil"},
        "herkunft": {"art": "lightos", "lizenz": "eigen"},
        "autor": "Test", "geprueft": {"ok": False, "wie": "Test"},
        "modi": [{"name": "3-Kanal", "kanaele": [
            {"name": "Rot", "attribut": "color_r", "default": 0, "highlight": 255},
            {"name": "Gruen", "attribut": "color_g", "default": 0, "highlight": 255},
            {"name": "Blau", "attribut": "color_b", "default": 0, "highlight": 255},
        ]}],
    }
    d.update(kopf)
    return d


# ── Regeln (rein) ────────────────────────────────────────────────────────────

class RegelnTest(unittest.TestCase):

    def test_keine_angabe(self):
        self.assertEqual(AW.normalisiere(0, 0), (0.0, 0.0))
        self.assertEqual(AW.normalisiere(None, None), (0.0, 0.0))
        self.assertEqual(AW.normalisiere("x", -5), (0.0, 0.0))
        self.assertIsNone(AW.zu_daten(0, 0))
        self.assertEqual(AW.text(0, 0), "")

    def test_fest_und_spanne(self):
        self.assertEqual(AW.normalisiere(25), (25.0, 25.0))
        self.assertEqual(AW.normalisiere(0, 30), (30.0, 30.0))
        self.assertEqual(AW.normalisiere(40, 8), (8.0, 40.0))   # getauscht
        self.assertEqual(AW.normalisiere(0.2, 999), (1.0, 170.0))  # geklemmt
        self.assertEqual(AW.zu_daten(25, 25), 25)
        self.assertEqual(AW.zu_daten(8, 40), [8, 40])
        self.assertEqual(AW.aus_daten([8, 40]), (8.0, 40.0))
        self.assertEqual(AW.aus_daten(12.5), (12.5, 12.5))
        self.assertEqual(AW.text(8, 40), "8–40° (Zoom)")


# ── Datenbank + Bibliotheksformat ────────────────────────────────────────────

class _DbFall(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.path = path
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)
        p = mock.patch.object(FDB, "_engine", self.engine)
        p.start()
        self.addCleanup(p.stop)
        from src.core.app_state import clear_channel_cache
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)

    def _winkel(self, pid):
        with Session(self.engine) as s:
            p = s.get(FixtureProfile, pid)
            return (p.beam_angle_min, p.beam_angle_max)


class MigrationTest(unittest.TestCase):

    def test_alte_fixtures_db_bekommt_die_spalten(self):
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
        self.assertIn("beam_angle_min", cols)
        self.assertIn("beam_angle_max", cols)


class BibliothekTest(_DbFall):

    def test_pruefung(self):
        self.assertEqual(BF.pruefe(_datei(abstrahlwinkel=25)), [])
        self.assertEqual(BF.pruefe(_datei(abstrahlwinkel=[8, 40])), [])
        self.assertEqual(BF.pruefe(_datei()), [])
        for falsch in (0, 200, [40, 8], [1, 2, 3], "25", True):
            befunde = BF.pruefe(_datei(abstrahlwinkel=falsch))
            self.assertTrue(any("abstrahlwinkel" in b for b in befunde), falsch)

    def _import_export(self, daten):
        tmp = tempfile.mkdtemp()
        datei = os.path.join(tmp, "p.json")
        with open(datei, "w", encoding="utf-8") as fh:
            json.dump(daten, fh)
        pid = BF.importiere(datei, engine=self.engine)
        return pid, BF.exportiere(pid, engine=self.engine)

    def test_import_export_mit_zoom_spanne(self):
        pid, raus = self._import_export(_datei(abstrahlwinkel=[8, 40]))
        self.assertEqual(self._winkel(pid), (8.0, 40.0))
        self.assertEqual(raus.get("abstrahlwinkel"), [8, 40])
        self.assertEqual(BF.pruefe(raus), [])

    def test_import_export_fest(self):
        pid, raus = self._import_export(_datei(abstrahlwinkel=25))
        self.assertEqual(self._winkel(pid), (25.0, 25.0))
        self.assertEqual(raus.get("abstrahlwinkel"), 25)

    def test_ohne_angabe_bleibt_das_feld_weg(self):
        pid, raus = self._import_export(_datei())
        self.assertEqual(self._winkel(pid), (0.0, 0.0))
        self.assertNotIn("abstrahlwinkel", raus)


# ── Generator + Editor ───────────────────────────────────────────────────────

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
            model="Kegel Gen", short_name="KGEN64", abstrahlwinkel=(40, 8),
            modes=[gen_module.GenMode("Default", gen_module.beispiel_kanaele())])
        payload = gen_module.build_profile_payload(model)
        self.assertEqual((payload["beam_angle_min"], payload["beam_angle_max"]),
                         (8.0, 40.0))
        pid = gen_module.save_generated_profile(payload, engine=self.engine)
        self.assertEqual(self._winkel(pid), (8.0, 40.0))
        self.assertIn("Abstrahlwinkel: 8–40° (Zoom)",
                      gen_module.model_to_markdown(model))

    def test_ohne_angabe_null(self):
        model = gen_module.GeneratorModel(
            model="Kegel Gen0", short_name="KGEN0",
            modes=[gen_module.GenMode("Default", gen_module.beispiel_kanaele())])
        pid = gen_module.save_generated_profile(
            gen_module.build_profile_payload(model), engine=self.engine)
        self.assertEqual(self._winkel(pid), (0.0, 0.0))

    def test_vorlage_traegt_den_winkel_in_den_dialog(self):
        model = gen_module.model_from_daten(_datei(abstrahlwinkel=[10, 30]))
        self.assertEqual(model.abstrahlwinkel, (10.0, 30.0))
        dlg = gen_module.FixtureGeneratorDialog(model=model)
        self.addCleanup(dlg.deleteLater)
        feld = dlg._abstrahlwinkel
        self.assertEqual(feld.werte(), (10.0, 30.0))
        self.assertIn("Abstrahlwinkel", feld.spin_eng.toolTip())
        feld.setze(22)
        dlg._sync_all()
        self.assertEqual(dlg._model.abstrahlwinkel, (22.0, 22.0))


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

    def _neu(self, eng, weit, short_name):
        dlg = editor_module.FixtureEditorDialog()
        self.addCleanup(dlg.deleteLater)
        dlg._cb_manufacturer.setEditText("Eigenbau FM64")
        dlg._edit_name.setText("Editor Kegel " + short_name)
        dlg._edit_short.setText(short_name)
        dlg._tabs.currentWidget()._add_channel()
        dlg._abstrahlwinkel.spin_eng.setValue(eng)
        dlg._abstrahlwinkel.spin_weit.setValue(weit)
        dlg._save()
        self.assertIsNotNone(dlg.saved_id, "Editor hat nicht gespeichert")
        return dlg.saved_id

    def test_editor_speichert_laedt_und_exportiert(self):
        pid = self._neu(12, 36, "EDKEG64")
        self.assertEqual(self._winkel(pid), (12.0, 36.0))
        dlg = editor_module.FixtureEditorDialog(fixture_id=pid)
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg._abstrahlwinkel.werte(), (12.0, 36.0))
        self.assertIn("Abstrahlwinkel", dlg._abstrahlwinkel.toolTip())
        # Aendern + Speichern am bestehenden Profil
        dlg._abstrahlwinkel.setze(20)
        dlg._save()
        self.assertEqual(self._winkel(pid), (20.0, 20.0))

    def test_editor_ohne_angabe(self):
        pid = self._neu(0, 0, "EDKEG0")
        self.assertEqual(self._winkel(pid), (0.0, 0.0))


# ── Nutzlast des 3D-Visualizers ──────────────────────────────────────────────

class NutzlastTest(_DbFall):

    def _profil(self, wmin, wmax, short_name):
        model = gen_module.GeneratorModel(
            model="Nutzlast " + short_name, short_name=short_name,
            abstrahlwinkel=(wmin, wmax),
            modes=[gen_module.GenMode("Default", gen_module.beispiel_kanaele())])
        return gen_module.save_generated_profile(
            gen_module.build_profile_payload(model), engine=self.engine)

    def _patched(self, pid):
        return PatchedFixture(fid=7, label="P", fixture_profile_id=pid,
                              mode_name="Default", universe=1, address=1,
                              channel_count=3, fixture_type="par")

    def test_winkel_kommt_in_der_nutzlast_an(self):
        d = _dict_for(self._patched(self._profil(10, 30, "NUTZ64")))
        self.assertEqual((d["beamAngleMin"], d["beamAngleMax"]), (10.0, 30.0))

    def test_ohne_angabe_null(self):
        d = _dict_for(self._patched(self._profil(0, 0, "NUTZ0")))
        self.assertEqual((d["beamAngleMin"], d["beamAngleMax"]), (0.0, 0.0))

    def test_geaenderter_winkel_baut_platziertes_geraet_neu(self):
        """Review FM-64: Editor/Generator speichern -> ``profil_geaendert`` ->
        ``patch_changed``. Der Kegel wird nur beim Anlegen gebaut — ohne Abgleich
        behielte ein schon platziertes Geraet den alten Winkel."""
        from unittest.mock import MagicMock
        from src.core.app_state import clear_channel_cache
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        pid = self._profil(10, 30, "NEU64")
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
            p = s.get(FixtureProfile, pid)
            p.beam_angle_min, p.beam_angle_max = 20.0, 20.0
            s.commit()
        clear_channel_cache()                               # profil_geaendert
        VisualizerBridge._nullpunkte_nachziehen(fake)
        self.assertEqual(fake.fixtureAdded.emit.call_count, 1)
        d = json.loads(fake.fixtureAdded.emit.call_args.args[0])
        self.assertEqual((d["beamAngleMin"], d["beamAngleMax"]), (20.0, 20.0))
        VisualizerBridge._nullpunkte_nachziehen(fake)       # nichts Neues
        self.assertEqual(fake.fixtureAdded.emit.call_count, 1)


if __name__ == "__main__":
    unittest.main()
