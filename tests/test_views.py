"""Headless smoke tests for key UI views/widgets."""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_virtualconsole_widgets_and_canvas():
    _app()
    from src.ui.virtualconsole import (
        VCButton, VCSlider, VCXYPad, VCLabel,
        VCCueList, VCSpeedDial, VCFrame, VCCanvas,
    )

    VCButton()
    VCSlider()
    VCXYPad()
    VCLabel()
    VCCueList()
    VCSpeedDial()
    VCFrame()
    canvas = VCCanvas()

    canvas._add_widget("VCButton", QPoint(10, 10))
    dumped = canvas.to_dict()
    assert len(dumped["widgets"]) == 1


def test_virtualconsole_bank_assignment():
    _app()
    from src.ui.virtualconsole import VCCanvas

    canvas = VCCanvas()
    # Neu angelegtes Widget landet auf der aktiven Bank.
    canvas.set_active_bank(0)
    w0 = canvas._add_widget("VCButton", QPoint(0, 0))
    assert w0.bank == 0
    canvas.set_active_bank(1)
    w1 = canvas._add_widget("VCButton", QPoint(0, 0))
    assert w1.bank == 1

    # Aktiv = Bank 1: nur w1 ist auf der Bank / sichtbar.
    assert canvas.on_active_bank(w1) is True
    assert canvas.on_active_bank(w0) is False
    assert w1.isVisibleTo(canvas) is True
    assert w0.isVisibleTo(canvas) is False

    # Bank-Wechsel dreht die Sichtbarkeit um.
    canvas.set_active_bank(0)
    assert canvas.on_active_bank(w0) is True
    assert canvas.on_active_bank(w1) is False

    # "Alle Banks" (-1) ist auf jeder Bank aktiv.
    w0._set_bank(-1)
    canvas.set_active_bank(7)
    assert canvas.on_active_bank(w0) is True


def test_virtualconsole_bank_roundtrip():
    _app()
    from src.ui.virtualconsole import VCCanvas
    from src.ui.virtualconsole.vc_widget import VCWidget

    canvas = VCCanvas()
    canvas.set_active_bank(2)
    canvas._add_widget("VCButton", QPoint(5, 5))      # -> Bank 2
    canvas._add_widget("VCLabel", QPoint(9, 9))       # -> Bank 2
    d = canvas.to_dict()
    assert all(w["bank"] == 2 for w in d["widgets"])

    canvas2 = VCCanvas()
    canvas2.from_dict(d)
    banks = [c.bank for c in canvas2.findChildren(VCWidget)]
    assert banks and all(b == 2 for b in banks)


def test_core_views_smoke():
    _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView
    from src.ui.views.simple_desk import SimpleDeskView
    from src.ui.views.efx_view import EfxView
    from src.ui.views.rgb_matrix_view import RgbMatrixView

    VirtualConsoleView()

    desk = SimpleDeskView()
    assert len(desk._faders) == 512

    # EFX/RGB-Matrix sind echte Funktionen im (geteilten) FunctionManager-
    # Singleton; daher Delta statt Absolutwert pruefen.
    efx = EfxView()
    n0 = len(efx._instances)
    efx._add_efx()
    assert len(efx._instances) == n0 + 1

    rgb = RgbMatrixView()
    m0 = len(rgb._instances)
    rgb._add()
    assert len(rgb._instances) == m0 + 1


def test_qxf_import_dialog_smoke():
    _app()
    from src.ui.widgets.qxf_import_dialog import QxfImportDialog

    QxfImportDialog()


def test_virtualconsole_popout_then_edit_no_crash():
    """Regression: Popout auf/zu darf den Canvas nicht zerstoeren, sonst kracht
    der naechste 'Bearbeiten'-Klick (VCCanvas already deleted)."""
    _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView

    v = VirtualConsoleView()
    v._popout_canvas()
    assert v._popout_window is not None
    v._popout_window.close()                 # closeEvent -> Canvas zurueck
    assert v._canvas_alive()                 # Canvas lebt noch

    # Bearbeiten + Widget hinzufuegen funktioniert nach dem Popout-Zyklus.
    v._btn_edit.setChecked(True)
    v._add_widget("VCButton")
    assert len(v.to_dict()["widgets"]) == 1

    # Mehrfaches Popout auf/zu bleibt stabil.
    v._popout_canvas(); v._popout_window.close()
    v._popout_canvas(); v._popout_window.close()
    assert v._canvas_alive()


def test_toolbar_add_cascades_and_selects():
    """UXT-06: Zwei Toolbar-Klicks legen VERSETZTE Widgets an (nicht deckungs-
    gleich in der Mitte) und wählen das jeweils neue aus."""
    _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView

    v = VirtualConsoleView()
    selected = []
    v._canvas.widget_selected.connect(lambda w: selected.append(w))
    v._btn_edit.setChecked(True)

    v._add_widget("VCButton")
    v._add_widget("VCButton")
    v._add_widget("VCButton")

    widgets = v.to_dict()["widgets"]
    assert len(widgets) == 3
    positions = {(w["x"], w["y"]) for w in widgets}
    assert len(positions) == 3, f"Widgets überlappen: {positions}"

    # Jeder Add wählt das neue Widget aus (Inspector-Bindung).
    assert selected and selected[-1] is not None

    # Kaskade startet je Bearbeiten-Sitzung neu.
    v._btn_edit.setChecked(False)
    v._btn_edit.setChecked(True)
    assert v._add_cascade == 0


def test_toolbar_add_cascade_wraps_on_canvas():
    """UXT-06: Die Kaskade wächst nicht endlos aus dem Canvas — nach `span`
    Stufen fängt sie wieder vorn an, alle Positionen bleiben >= 0."""
    _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView

    v = VirtualConsoleView()
    v._btn_edit.setChecked(True)
    for _ in range(20):
        v._add_widget("VCButton")
    for w in v.to_dict()["widgets"]:
        assert w["x"] >= 0 and w["y"] >= 0
