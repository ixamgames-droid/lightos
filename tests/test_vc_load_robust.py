"""Regression: ein einzelnes defektes/unbekanntes Widget darf NICHT das Laden der
restlichen VC abbrechen (sonst verschwindet fast die ganze Konsole). Ausgeloest durch
eine Button-Aktion, die der ladende Code (andere Version) nicht kennt."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])


# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets WIRKLICH
# abbauen. `deleteLater()` allein stellt `DeferredDelete` nie zu — die Objekte
# ueberleben mitsamt Kindern, Signalen und (bei Views) Renderern. Segmentiert
# faellt das nicht auf, weil jede Datei allein laeuft; in einem Prozess mit
# genug angesammeltem Zustand ist es dieselbe Klasse Zeitzuender, die vor
# XPLAT-09 neun scheinbar gruene viz-Dateien zum Segfault brachte.
# Muster + Begruendung: tests/_qt_lifecycle.py, Vorbild test_views.py.
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    # QApplication lokal importieren: manche Dateien holen es nur INNERHALB
    # ihrer Tests, dann gibt es den Modulnamen hier nicht.
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


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
