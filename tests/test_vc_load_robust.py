"""Regression: ein einzelnes defektes/unbekanntes Widget darf NICHT das Laden der
restlichen VC abbrechen (sonst verschwindet fast die ganze Konsole). Ausgeloest durch
eine Button-Aktion, die der ladende Code (andere Version) nicht kennt."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])


def test_button_unknown_action_falls_back_to_toggle():
    from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
    b = VCButton("x")
    b.apply_dict({"action": "SomeFutureActionXYZ", "caption": "x"})
    assert b.action == ButtonAction.TOGGLE, "unbekannte Aktion crasht/verwirft statt Fallback"


def test_button_known_new_action_loads():
    from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
    b = VCButton("y")
    b.apply_dict({"action": "AutoSync", "caption": "y"})
    assert b.action == ButtonAction.AUTO_SYNC


def test_canvas_skips_bad_widget_keeps_rest():
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_button import VCButton
    canvas = VCCanvas()
    canvas.from_dict({"widgets": [
        {"type": "VCButton", "action": "FunctionToggle", "x": 0, "y": 0, "w": 60, "h": 60},
        {"type": "GarbageWidgetType", "x": 70, "y": 0, "w": 60, "h": 60},          # unbekannter Typ
        {"type": "VCButton", "action": "FunctionToggle", "x": 140, "y": 0, "w": 60, "h": 60},
    ]})
    btns = canvas.findChildren(VCButton)
    assert len(btns) == 2, f"defektes Widget hat das Laden abgebrochen: nur {len(btns)} Buttons"
    canvas.deleteLater()
