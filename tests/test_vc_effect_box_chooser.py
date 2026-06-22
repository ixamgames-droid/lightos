"""Effekt-Editor-Box: ⚙-Auswahlmenue + „Namen primaer"-Umbau.

Deckt die neue Funktionalitaet ab, die der Dialog-Smoke-Test (exec→Rejected)
nicht erreicht:
  - ``VCEffectEditor.open_control_chooser`` baut die gewaehlten Aspekte als
    Bedien-Widgets IN die Box (ein Undo) und dedupliziert beim erneuten Oeffnen.
  - ``VCDropPanel(for_box=True)`` blendet die „Als Box gruppieren"-Checkbox aus.
  - ``VCSpeedDial`` defaultet auf Ziel FUNCTION (Name) statt Executor-Slot.
  - Properties-Dialoge speichern korrekt (exec→Accepted), auch mit dem in die
    „Erweitert"-Sektion verschobenen Roh-ID-/Slot-Feld.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QDialog


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def accept(monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)


# ── Issue 2: Namen primaer ────────────────────────────────────────────────────

def test_speeddial_defaults_to_function_target():
    _app()
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    assert VCSpeedDial().target_mode == SpeedTarget.FUNCTION


def test_dropped_speeddial_targets_function():
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    c = VCCanvas()
    dial = c._add_widget("VCSpeedDial", QPoint(10, 10))
    assert c._apply_function_to_special(dial, 7, "Matrix Welle", interactive=True)
    assert dial.target_mode == SpeedTarget.FUNCTION
    assert dial.function_id == 7


def test_for_box_panel_hides_group_checkbox():
    _app()
    from src.ui.virtualconsole.vc_drop_panel import VCDropPanel
    assert VCDropPanel(1, for_box=True)._box_cb is None
    assert VCDropPanel(1, for_box=False)._box_cb is not None


def test_speeddial_save_path(accept):
    _app()
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    for mode in (SpeedTarget.FUNCTION, SpeedTarget.EXECUTOR, SpeedTarget.TEMPO_BUS,
                 SpeedTarget.TEMPO_BUS_MULT, SpeedTarget.SPEED_NODE):
        w = VCSpeedDial()
        w.target_mode = mode
        w.function_id = 5
        w._open_properties()                      # baut + speichert (Accept)
        assert w.target_mode == mode              # Modus bleibt erhalten


def test_slider_and_button_save_path(accept):
    _app()
    from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
    from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
    s = VCSlider()
    s.mode = SliderMode.PLAYBACK
    s.function_id = 3
    s._open_properties()
    assert s.function_id == 3                      # Slot/Roh-ID via Erweitert erhalten
    b = VCButton()
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = 4
    b._open_properties()
    assert b.action == ButtonAction.FUNCTION_TOGGLE


# ── Issue 1: ⚙-Auswahlmenue der Effekt-Editor-Box ─────────────────────────────

def _fake_results():
    from src.ui.virtualconsole.smart_drop_dialog import SmartDropResult
    from src.ui.virtualconsole.vc_button import ButtonAction
    from src.ui.virtualconsole.vc_slider import SliderMode
    return [
        SmartDropResult(widget_type="VCButton", function_id=9, caption="An/Aus",
                        action=ButtonAction.FUNCTION_TOGGLE),
        SmartDropResult(widget_type="VCSlider", function_id=9, caption="Tempo",
                        slider_mode=SliderMode.EFFECT_SPEED),
    ]


def test_box_chooser_builds_controls_and_dedups(monkeypatch):
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_drop_panel import VCDropPanel
    from src.ui.virtualconsole.vc_widget import VCWidget

    monkeypatch.setattr(VCDropPanel, "run", lambda self: _fake_results())

    c = VCCanvas()
    box = c._add_widget("VCEffectEditor", QPoint(20, 20))
    box.effect_id = 9                              # ohne echten Effekt (Chooser gestubbt)

    box.open_control_chooser()
    kids = box.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    assert len(kids) == 2
    assert sorted(k.caption for k in kids) == ["An/Aus", "Tempo"]

    # Erneut mit denselben Aspekten -> Dedup, keine Duplikate.
    box.open_control_chooser()
    kids2 = box.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    assert len(kids2) == 2


def test_box_no_auto_sliders_on_bind():
    """set_effect baut KEINE festen Auto-Slider mehr (frueher 3 Stueck)."""
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_widget import VCWidget
    c = VCCanvas()
    box = c._add_widget("VCEffectEditor", QPoint(0, 0))
    box.set_effect(9)                              # open_chooser=False (Default)
    kids = box.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    assert kids == []                              # keine ungewollten Regler


def test_effect_editor_in_droppable_types():
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_effect_editor import VCEffectEditor
    assert VCEffectEditor in VCCanvas._droppable_types()


def test_rebind_to_different_effect_clears_old_controls(monkeypatch):
    """Anderer Effekt auf eine befuellte Box -> alte (zum alten Effekt gehoerende)
    Regler verschwinden (kein stiller Steuer-auf-falschen-Effekt-Fehler)."""
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_drop_panel import VCDropPanel

    monkeypatch.setattr(VCDropPanel, "run", lambda self: _fake_results())  # gebunden an fid 9
    c = VCCanvas()
    box = c._add_widget("VCEffectEditor", QPoint(0, 0))
    box.set_effect(9)
    box.open_control_chooser()
    assert len(box._control_children()) == 2

    # Anderen Effekt (fid 10) drauf ziehen (nicht-interaktiv -> kein Chooser).
    assert c._apply_function_to_special(box, 10, "Andere Matrix", interactive=False)
    assert box.effect_id == 10
    assert box._control_children() == []          # alte Regler (fid 9) entfernt


def test_build_default_controls_headless(monkeypatch):
    """build_default_controls baut Standard-Regler aus den Faehigkeiten (Generator-
    Pfad) — ohne interaktives Auswahlmenue."""
    _app()
    from src.ui.virtualconsole import vc_effect_meta
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_widget import VCWidget

    class _Caps:
        has_speed = True
        has_intensity = True
    monkeypatch.setattr(vc_effect_meta, "function_capabilities", lambda fid: _Caps())

    c = VCCanvas()
    box = c._add_widget("VCEffectEditor", QPoint(0, 0))
    box.effect_id = 9
    built = box.build_default_controls()
    assert len(built) == 2
    kids = box.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    assert len(kids) == 2
    # Idempotent: erneut aufrufen -> keine Verdopplung (Box schon befuellt).
    assert box.build_default_controls() == []


# ── Touch: adaptiver ⚙-Knopf (grosse Tap-Ziele, kein Drag noetig) ─────────────

def test_gear_adapts_to_state_in_edit_mode():
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_slider import VCSlider
    c = VCCanvas()
    box = c._add_widget("VCEffectEditor", QPoint(0, 0))
    # Im Run-Modus (kein Edit) ist der ⚙ unsichtbar -> kein versehentliches Antippen.
    # (isVisibleTo(box) statt isVisible(): die Box selbst wird im Test nie gezeigt.)
    box.set_edit_mode(False)
    box._reposition_chrome()
    assert not box._gear_btn.isVisibleTo(box)
    # Edit-Modus, ungebunden -> grosser „Effekt wählen"-Tap-Knopf.
    box.set_edit_mode(True)
    assert box._gear_btn.isVisibleTo(box)
    assert "Effekt wählen" in box._gear_btn.text()
    # Gebunden, aber leer -> grosser „Bedienelemente wählen"-Knopf.
    box.set_effect(9)
    assert "Bedienelemente wählen" in box._gear_btn.text()
    # Befuellt -> kompaktes Eck-Zahnrad.
    box.add_effect_child(VCSlider("x"), 0)
    box._reposition_chrome()
    assert box._gear_btn.text() == "⚙"


def test_gear_click_dispatch(monkeypatch):
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    c = VCCanvas()
    box = c._add_widget("VCEffectEditor", QPoint(0, 0))
    calls = []
    monkeypatch.setattr(box, "choose_effect", lambda: calls.append("choose"))
    monkeypatch.setattr(box, "open_control_chooser", lambda: calls.append("chooser"))
    box._on_gear_clicked()           # ungebunden -> Effekt waehlen
    box.effect_id = 9
    box._on_gear_clicked()           # gebunden -> Bedienelement-Auswahl
    assert calls == ["choose", "chooser"]


def test_choose_effect_binds_by_name(monkeypatch):
    """choose_effect: Effekt per Name -> set_effect(open_chooser=True)."""
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_drop_panel import VCDropPanel
    from PySide6.QtWidgets import QInputDialog

    # Funktionsliste + Dialog + Chooser stubben.
    monkeypatch.setattr("src.ui.virtualconsole.target_list_editor._all_functions",
                        lambda: [(7, "Matrix Welle  [RGBMatrix #7]")])
    monkeypatch.setattr(QInputDialog, "getItem",
                        staticmethod(lambda *a, **k: ("Matrix Welle  [RGBMatrix #7]", True)))
    monkeypatch.setattr(VCDropPanel, "run", lambda self: [])   # kein Regler gewaehlt

    c = VCCanvas()
    box = c._add_widget("VCEffectEditor", QPoint(0, 0))
    box.choose_effect()
    assert box.effect_id == 7
