"""Welle 3 / Cluster M: Snap-Editor + SnapLibrary-Mutations-API.

Nicht-Matrix-Snaps bekommen ein Bearbeiten-Overlay (Liste der programmierten
Kanaele). Werte aendern/entfernen laeuft ueber neue SnapLibrary-Setter, geklemmt.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.snap_library import get_snap_library, SnapLibrary


def _app():
    return QApplication.instance() or QApplication([])


def test_library_mutation_api():
    lib = SnapLibrary()
    snap = lib.add_snap("S1", "", {1: {"intensity": 255, "color_r": 128}, 2: {"dimmer": 100}})
    assert lib.set_snap_value(snap.id, 1, "intensity", 200)
    assert snap.values[1]["intensity"] == 200
    lib.set_snap_value(snap.id, 1, "color_r", 999)      # klemmt auf 255
    assert snap.values[1]["color_r"] == 255
    assert lib.remove_snap_attr(snap.id, 2, "dimmer")
    assert 2 not in snap.values                          # leeres Gerät entfernt
    assert lib.remove_snap_attr(snap.id, 2, "dimmer") is False   # schon weg
    lib.set_snap_values(snap.id, {3: {"intensity": 300}})        # normalisiert+klemmt
    assert snap.values == {3: {"intensity": 255}}
    assert lib.set_snap_value(99999, 1, "x", 1) is False         # unbekannter Snap


def test_snap_editor_loads_edits_removes():
    _app()
    from src.ui.views.snap_editor import SnapEditor
    lib = get_snap_library()
    snap = lib.add_snap("S2", "", {1: {"intensity": 255, "color_r": 128}, 2: {"dimmer": 100}})
    ed = SnapEditor(snap)
    assert ed._tbl.rowCount() == 3        # 3 programmierte Kanäle (1:2 + 2:1)
    ed._on_value(1, "intensity", 77)
    assert lib.get(snap.id).values[1]["intensity"] == 77
    ed._remove(2, "dimmer")
    assert 2 not in lib.get(snap.id).values
    assert ed._tbl.rowCount() == 2        # neu geladen ohne die entfernte Zeile
