"""Welle 4 (Box-Restscope / FRM-01): In-Box-Löschen ist verdrahtet UND undobar.

- `add_child_to_page` übergibt Delete-Ownership an die Box (früher gar nicht
  verdrahtet -> Snap-in-Widget hing weiter an der Canvas).
- `_remove_child` zieht VOR dem Entfernen einen Canvas-Gesamt-Snapshot
  -> Strg+Z holt das in der Box gelöschte Widget zurück.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, Qt


def _app():
    return QApplication.instance() or QApplication([])


def _kids(frame):
    from src.ui.virtualconsole.vc_widget import VCWidget
    return frame.findChildren(VCWidget,
                              options=Qt.FindChildOption.FindDirectChildrenOnly)


def test_in_box_delete_is_undoable():
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_frame import VCFrame
    canvas = VCCanvas()
    frame = canvas._add_widget("VCFrame", QPoint(40, 30))
    child = frame._add_child_widget("VCButton")
    assert child is not None and child in _kids(frame)

    n0 = len(canvas._undo_stack)
    child.delete_requested.emit()                 # wie Rechtsklick -> „Löschen"
    assert child not in _kids(frame)              # weg
    assert len(canvas._undo_stack) == n0 + 1      # Undo-Punkt VOR dem Entfernen

    canvas.undo()
    new_frames = canvas.findChildren(
        VCFrame, options=Qt.FindChildOption.FindDirectChildrenOnly)
    assert new_frames
    assert any(type(k).__name__ == "VCButton" for k in _kids(new_frames[0]))


def test_add_child_to_page_transfers_delete_ownership():
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    canvas = VCCanvas()
    frame = canvas._add_widget("VCFrame", QPoint(40, 30))
    btn = canvas._add_widget("VCButton", QPoint(20, 20))   # zuerst auf der Canvas
    frame.add_child_to_page(btn, 0)                        # in die Box (Snap-in-Pfad)
    assert btn.parent() is frame

    n0 = len(canvas._undo_stack)
    btn.delete_requested.emit()
    assert btn not in _kids(frame)                # Box-Kind entfernt
    assert len(canvas._undo_stack) == n0 + 1      # über die (undobare) Box gelaufen


def test_effect_editor_box_highlights_as_unit():
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    canvas = VCCanvas()
    canvas.set_edit_mode(True)                    # Highlight nur im Edit-Modus
    box = canvas._add_widget("VCEffectEditor", QPoint(40, 30))
    box.effect_id = 7
    # Die Box bindet ihren Effekt über effect_id -> muss in der Gruppe zählen.
    assert 7 in canvas._effect_ids_of(box)
    # Effekt 7 hervorheben -> Box leuchtet als EINHEIT (Amber-Rahmen-Flag).
    canvas.highlight_effects([7])
    assert box._effect_highlight is True
    canvas.highlight_effects([])                  # aufheben
    assert box._effect_highlight is False
