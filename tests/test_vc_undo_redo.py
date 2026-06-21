"""Undo/Redo im VC-Editor (Snapshot-Verlauf): Hinzufuegen + Loeschen rueckgaengig/wiederholbar.
Deckt Davids Hauptfall ab: ein geloeschtes Widget per Strg+Z wieder herstellen."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, Qt

_app = QApplication.instance() or QApplication([])

from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_button import VCButton


def _n(canvas):
    return len(canvas.to_dict()["widgets"])


def _direct_buttons(canvas):
    return canvas.findChildren(VCButton, options=Qt.FindChildOption.FindDirectChildrenOnly)


def test_undo_redo_delete_and_add():
    c = VCCanvas()
    c._add_widget("VCButton", QPoint(0, 0))      # user-add (d=None) -> Undo-Punkt
    c._add_widget("VCButton", QPoint(70, 0))
    assert _n(c) == 2

    # Loeschen -> Undo stellt wieder her (Davids Fall)
    c._remove_widget(_direct_buttons(c)[0])
    assert _n(c) == 1
    c.undo()
    assert _n(c) == 2, "Strg+Z nach Loeschen stellt das Widget nicht wieder her"
    c.redo()
    assert _n(c) == 1, "Wiederholen geht nicht"

    # mehrere Schritte zurueck (auch die Adds)
    c.undo()                 # Loeschen erneut rueckgaengig
    assert _n(c) == 2
    c.undo()                 # 2. Add rueckgaengig
    assert _n(c) == 1
    c.undo()                 # 1. Add rueckgaengig
    assert _n(c) == 0


def test_undo_noop_when_empty():
    c = VCCanvas()
    c.undo(); c.redo()       # darf nicht crashen
    assert _n(c) == 0


def test_move_undo_restores_geometry():
    # Verschieben ist ein Undo-Punkt: push_undo_snapshot(Vorher) + undo() stellt
    # die alte Position wieder her (so verdrahtet es VCWidget.mouseRelease).
    c = VCCanvas()
    c._add_widget("VCButton", QPoint(10, 10))
    btn = _direct_buttons(c)[0]
    orig = (btn.x(), btn.y())
    before = c.to_dict()
    btn.move(80, 90)
    c.push_undo_snapshot(before)
    c.undo()
    btn2 = _direct_buttons(c)[0]
    assert (btn2.x(), btn2.y()) == orig


def test_property_edit_creates_undo_point():
    # _edit_properties erfasst den Vorher-Stand und legt ihn nur bei echter
    # Aenderung auf den Undo-Stapel (hier _open_properties gemockt = aendert caption).
    import types
    c = VCCanvas()
    c._add_widget("VCButton", QPoint(0, 0))
    btn = _direct_buttons(c)[0]
    btn.caption = "Alt"
    c._undo_stack.clear(); c._redo_stack.clear()
    btn._open_properties = types.MethodType(
        lambda self: setattr(self, "caption", "Neu"), btn)
    btn._edit_properties()
    assert btn.caption == "Neu"
    assert c.can_undo()
    c.undo()
    assert _direct_buttons(c)[0].caption == "Alt"


def test_property_edit_no_change_no_undo():
    # Dialog ohne Aenderung -> KEIN Undo-Punkt (kein No-op-Strg+Z).
    import types
    c = VCCanvas()
    c._add_widget("VCButton", QPoint(0, 0))
    btn = _direct_buttons(c)[0]
    c._undo_stack.clear(); c._redo_stack.clear()
    btn._open_properties = types.MethodType(lambda self: None, btn)
    btn._edit_properties()
    assert not c.can_undo()


def test_add_live_controls_is_single_undo_step():
    # Ein ganzes Live-Control-Kit (mehrere Widgets) = genau EIN Undo-Schritt.
    c = VCCanvas()
    n0 = len(c._undo_stack)
    created = c.add_live_controls(1, ["speed"], ["start"])
    assert len(created) == 2
    assert len(c._undo_stack) == n0 + 1
    c.undo()
    assert _n(c) == 0


def test_load_resets_history():
    c = VCCanvas()
    c._add_widget("VCButton", QPoint(0, 0))
    c.from_dict({"widgets": [
        {"type": "VCButton", "action": "FunctionToggle", "x": 0, "y": 0, "w": 60, "h": 60},
        {"type": "VCButton", "action": "FunctionToggle", "x": 70, "y": 0, "w": 60, "h": 60},
    ]})
    assert _n(c) == 2
    assert not c.can_undo(), "Show-Laden muss den Undo-Verlauf zuruecksetzen"
