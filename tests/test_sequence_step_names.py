"""Welle-1-Rest (F): SequenceEditor zeigt Step-NAMEN statt der Roh-Werte.

Davids Beschwerde: im Chaser/Sequence-Step-Liste standen '0 0 0 … 255' je Step.
Jetzt: Spalte 1 = Step-Name (note), Werte nur im Tooltip + über einen „Werte…"-Button.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def test_sequence_editor_shows_step_name_not_values():
    _app()
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine.sequence import SequenceStep
    from src.ui.views.sequence_editor import SequenceEditor, COLS
    fm = get_function_manager()
    seq = fm.new_sequence("S")
    seq.steps.append(SequenceStep(values={"3": {"dimmer": 255}}, note="Intro",
                                  fade_in=0.0, hold=1.0, fade_out=0.0))
    seq.steps.append(SequenceStep(values={"5": {"red": 200}}, note="",
                                  fade_in=0.0, hold=1.0, fade_out=0.0))
    ed = SequenceEditor(seq)
    assert COLS[1] == "Schritt" and COLS[7] == "Werte"
    # Spalte 1 = Name (note), NICHT die Werte
    assert ed._tbl.item(0, 1).text() == "Intro"
    assert ed._tbl.item(1, 1).text() == "Schritt 2"          # leerer note -> Fallback
    # Roh-Werte nur noch im Tooltip
    assert "dimmer=255" in ed._tbl.item(0, 1).toolTip()
    # Spalte 7 = Werte-Editor-Button (kein Inline-Dump)
    assert ed._tbl.cellWidget(0, 7) is not None
