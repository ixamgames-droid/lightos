"""Integrationstest: Button-/Fader-Dialog mit der neuen „Steuert"-Liste oeffnet
fehlerfrei und uebernimmt die gebundenen Funktionen/Parameter (Round-Trip).

Der modale Dialog wird per gepatchtem QDialog.exec automatisch akzeptiert, sodass
der komplette Aufbau- + Accept-Pfad ausgefuehrt wird (faengt Verdrahtungsfehler ab)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QDialog

_app = QApplication.instance() or QApplication([])

from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.target_list_editor import TargetListEditor, SnapListEditor
from src.ui.virtualconsole.vc_xypad import VCXYPad


@pytest.fixture
def auto_accept(monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)


def test_button_dialog_roundtrips_targets(auto_accept):
    b = VCButton()
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = 3
    b.function_ids = [7, 11]
    b._open_properties()       # darf nicht crashen
    # „Steuert"-Liste war aus dem Bindungsstand befuellt -> Round-Trip erhaelt ihn
    assert b.function_id == 3
    assert b.function_ids == [7, 11]


def test_button_dialog_switch_list_replaces_raw_targets(monkeypatch):
    b = VCButton()
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = 3
    b.function_ids = [7, 11]

    def _accept_with_changed_targets(dlg):
        ed = dlg.findChild(TargetListEditor)
        assert ed is not None, "Schaltet-mit-Liste fehlt im Button-Dialog"
        ed.set_targets([11, 13])
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", _accept_with_changed_targets)
    b._open_properties()
    assert b.function_id == 11
    assert b.function_ids == [13]


def test_button_dialog_empty_switch_list_clears_targets(monkeypatch):
    b = VCButton()
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = 3
    b.function_ids = [7, 11]

    def _accept_with_empty_targets(dlg):
        ed = dlg.findChild(TargetListEditor)
        assert ed is not None, "Schaltet-mit-Liste fehlt im Button-Dialog"
        ed.set_targets([])
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", _accept_with_empty_targets)
    b._open_properties()
    assert b.function_id is None
    assert b.function_ids == []


def test_button_dialog_snap_list_replaces_raw_snap(monkeypatch):
    b = VCButton()
    b.action = ButtonAction.LIBRARY_SNAP
    b.snap_id = 4
    b.snap_ids = [5]

    def _accept_with_snap_targets(dlg):
        ed = dlg.findChild(SnapListEditor)
        assert ed is not None, "Snap-Zielliste fehlt im Button-Dialog"
        ed.set_targets([5, 6, 7])
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", _accept_with_snap_targets)
    b._open_properties()
    assert b.snap_id == 5
    assert b.snap_ids == [6, 7]


def test_slider_dialog_roundtrips_targets_and_params(auto_accept):
    s = VCSlider()
    s.mode = SliderMode.EFFECT_SPEED
    s.function_ids = [5, 9]
    s.function_id = 5
    s.param_keys_per_id = {5: "speed"}
    s._open_properties()
    assert s.function_ids == [5, 9]
    assert s.function_id == 5
    assert s.param_keys_per_id == {5: "speed"}


def test_xypad_dialog_roundtrips_efx(auto_accept):
    p = VCXYPad()
    p.mode = "area"
    p.efx_function_id = 8
    p._open_properties()
    assert p.efx_function_id == 8


def test_button_executor_mode_unaffected(auto_accept):
    # Executor-Toggle (Slot-Nummer) -> Editor ist unsichtbar/leer, Slot bleibt erhalten
    b = VCButton()
    b.action = ButtonAction.TOGGLE
    b.function_id = 2
    b.function_ids = []
    b._open_properties()
    assert b.function_id == 2
