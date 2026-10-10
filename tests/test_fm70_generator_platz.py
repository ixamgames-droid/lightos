"""FM-70 / DOC-65: Huerden im Fixture Generator, gefunden beim Anlegen des
EL-400RGB MK2 ueber die echte Oberflaeche (Bild-Werkzeug, echter Bildschirm).

1. Auf einem 1080er-Bildschirm wird der Dialog hoechstens ~1000 px hoch. Kopf
   (einspaltig), Hinweise und Live-Test (untereinander) liessen der
   Kanaltabelle EINE sichtbare Zeile, der Bereichstabelle ebenso.
2. Das Feld „Modus-Name“ aenderte den Namen im Modell, der Reiter hiess aber
   weiter „Default“.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def _dialog(hoehe=1000):
    _app()
    from src.ui.widgets.fixture_generator import (FixtureGeneratorDialog,
                                                  GenChannel, GenMode,
                                                  GeneratorModel)
    m = GeneratorModel(manufacturer="Laserworld", model="EL-400RGB MK2",
                       fixture_type="laser",
                       modes=[GenMode("Default", [GenChannel(f"K{i}")
                                                  for i in range(9)])])
    dlg = FixtureGeneratorDialog(None, model=m)
    dlg.resize(1200, hoehe)
    dlg.show()
    _app().processEvents()
    return dlg


def _zu(dlg):
    dlg._live.shutdown()
    dlg.close()
    dlg.deleteLater()
    _app().processEvents()


def test_kanaltabelle_zeigt_bei_1000px_mindestens_fuenf_zeilen():
    dlg = _dialog(1000)
    try:
        tab = dlg._tabs.currentWidget()
        tbl = tab._tbl
        sichtbar = tbl.viewport().height() // max(1, tbl.rowHeight(0))
        assert sichtbar >= 5, f"nur {sichtbar} Zeilen sichtbar"
        assert tab._range_editor._tbl.viewport().height() >= 4 * tbl.rowHeight(0)
    finally:
        _zu(dlg)


def test_modusname_benennt_den_reiter():
    dlg = _dialog()
    try:
        tab = dlg._tabs.currentWidget()
        tab._edit_name.setFocus()
        tab._edit_name.selectAll()
        QTest.keyClicks(tab._edit_name, "9-Kanal")
        QTest.keyClick(tab._edit_name, Qt.Key.Key_Return)
        _app().processEvents()
        assert tab.mode.name == "9-Kanal"
        assert dlg._tabs.tabText(dlg._tabs.indexOf(tab)) == "9-Kanal"
    finally:
        _zu(dlg)
