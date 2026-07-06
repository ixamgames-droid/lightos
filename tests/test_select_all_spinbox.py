"""UXT-11a: SelectAllSpinBox markiert bei Fokus den ganzen Inhalt, damit das
erste Eintippen den Wert ersetzt statt anzuhängen."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QApplication, QSpinBox

from src.ui.widgets.select_all_spinbox import SelectAllSpinBox


def _app():
    return QApplication.instance() or QApplication([])


def test_is_a_spinbox():
    _app()
    assert issubclass(SelectAllSpinBox, QSpinBox)


def test_focus_selects_all():
    app = _app()
    sb = SelectAllSpinBox()
    sb.setRange(0, 999)
    sb.setValue(42)
    # Kein Text markiert, solange nicht fokussiert.
    assert sb.lineEdit().selectedText() == ""
    sb.focusInEvent(QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason))
    app.processEvents()                      # der QTimer(0) feuert selectAll
    assert sb.lineEdit().selectedText() == "42"


def test_first_typed_digit_replaces_value():
    app = _app()
    sb = SelectAllSpinBox()
    sb.setRange(0, 999)
    sb.setValue(1)
    sb.focusInEvent(QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason))
    app.processEvents()
    # Bei markiertem Inhalt ersetzt eine getippte Ziffer den alten Wert
    # (statt „1"+„2" = „12"): das Line-Edit hat den Wert komplett selektiert.
    assert sb.lineEdit().selectedText() == "1"
