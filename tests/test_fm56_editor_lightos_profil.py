"""FM-56: Fixture-Editor — „Als LightOS-Profil exportieren/importieren“.

Export schreibt den (auch ungespeicherten) Editor-Inhalt als LightOS-Profil;
Import legt eine Datei als EIGENES Profil an und schliesst den Dialog wie
Speichern (``saved_id``). Dazu: die Listen des Editors (Typen, Attribute)
sind im Format bekannt — sonst koennte der Editor Profile bauen, die der
Export ablehnt.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from sqlalchemy import select                          # noqa: E402
from sqlalchemy.orm import Session                     # noqa: E402

from src.core.database import bibliothek_format as BF   # noqa: E402
from src.core.database.fixture_db import get_engine     # noqa: E402
from src.core.database.models import FixtureProfile     # noqa: E402
from src.ui.widgets import fixture_editor as editor_module  # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class EditorLightosProfilTest(unittest.TestCase):

    def setUp(self):
        self.wurzel = tempfile.mkdtemp(prefix="lightos_fm56_ed_")
        self.addCleanup(shutil.rmtree, self.wurzel, True)
        self.engine = get_engine(os.path.join(self.wurzel, "fixtures.db"))
        self.addCleanup(self.engine.dispose)
        p = mock.patch.object(editor_module, "engine", return_value=self.engine)
        p.start()
        self.addCleanup(p.stop)
        self.warnungen = []
        w = mock.patch.object(QMessageBox, "warning",
                              side_effect=lambda *a, **k: self.warnungen.append(a[2]))
        w.start()
        self.addCleanup(w.stop)

    def _dialog(self):
        dlg = editor_module.FixtureEditorDialog()
        dlg._cb_manufacturer.setCurrentText("Testwerk")
        dlg._edit_name.setText("Bar 2")
        dlg._edit_short.setText("BAR2")
        dlg._cb_type.setCurrentText("led_bar")
        dlg._spin_power.setValue(40)
        tab = dlg._tabs.widget(0)
        tab.channels = [
            {"name": "Dimmer", "attribute": "intensity", "default": 0, "highlight": 255,
             "segment": 0},
            {"name": "Weiss", "attribute": "color_w", "default": 0, "highlight": 255},
            {"name": "Strobe", "attribute": "shutter", "default": 0, "highlight": 0,
             "ranges": [{"range_from": 10, "range_to": 255, "name": "Strobe",
                         "kind": "strobe"},
                        {"range_from": 0, "range_to": 9, "name": "Offen", "kind": "open"}]},
        ]
        tab._rebuild_rows()
        return dlg

    def test_export_schreibt_gueltiges_profil(self):
        dlg = self._dialog()
        ziel = os.path.join(self.wurzel, "bar.json")
        self.assertEqual(dlg._lightos_export(ziel), ziel)
        d = BF.lade_datei(ziel)
        self.assertEqual((d["hersteller"], d["modell"], d["typ"], d["leistung_w"]),
                         ("Testwerk", "Bar 2", "led_bar", 40))
        kan = d["modi"][0]["kanaele"]
        self.assertEqual([k["attribut"] for k in kan], ["intensity", "color_w", "shutter"])
        self.assertEqual(kan[0].get("segment"), 0)
        self.assertEqual([b["von"] for b in kan[2]["bereiche"]], [0, 10])
        self.assertEqual(d["herkunft"], {"art": "lightos", "lizenz": "eigen"})
        self.assertEqual(self.warnungen, [])

    def test_export_mit_platzhalter_wird_abgelehnt(self):
        dlg = self._dialog()
        dlg._edit_name.setText(editor_module.PLATZHALTER_MODELL)
        ziel = os.path.join(self.wurzel, "nein.json")
        self.assertIsNone(dlg._lightos_export(ziel))
        self.assertFalse(os.path.exists(ziel))
        self.assertEqual(len(self.warnungen), 1)

    def test_import_legt_eigenes_profil_an(self):
        ziel = os.path.join(self.wurzel, "bar.json")
        self._dialog()._lightos_export(ziel)
        dlg = editor_module.FixtureEditorDialog()
        pid = dlg._lightos_import(ziel)
        self.assertIsNotNone(pid)
        self.assertEqual((dlg.saved_id, dlg._saved_id), (pid, pid))
        with Session(self.engine) as s:
            p = s.get(FixtureProfile, pid)
            self.assertEqual((p.source, p.name, p.manufacturer.name),
                             ("user", "Bar 2", "Testwerk"))
            self.assertEqual(p.modes[0].channels[0].segment, 0)
        # zweites Mal: Dublette -> Warnung, nichts angelegt
        self.assertIsNone(editor_module.FixtureEditorDialog()._lightos_import(ziel))
        self.assertEqual(len(self.warnungen), 1)
        with Session(self.engine) as s:
            self.assertEqual(len(s.scalars(select(FixtureProfile)
                                           .where(FixtureProfile.name == "Bar 2")).all()), 1)

    def test_import_ungueltig_meldet_befunde(self):
        ziel = os.path.join(self.wurzel, "kaputt.json")
        with open(ziel, "w", encoding="utf-8") as fh:
            json.dump({"format_version": 1}, fh)
        self.assertIsNone(editor_module.FixtureEditorDialog()._lightos_import(ziel))
        self.assertIn("hersteller", self.warnungen[0])


class ListenTest(unittest.TestCase):

    def test_editor_listen_sind_im_format_bekannt(self):
        self.assertEqual(set(editor_module.CHANNEL_ATTRS) - set(BF.ATTRIBUTE), set())
        self.assertEqual(set(editor_module.FIXTURE_TYPES), set(BF.TYPEN))


if __name__ == "__main__":
    unittest.main()
