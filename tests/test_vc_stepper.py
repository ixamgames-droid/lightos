"""VCStepper: diskrete int/select/bool-Parameter.

Das Widget bindet wie der Encoder an einen Effekt-Parameter und setzt
Zaehlwerte, Auswahlwerte und Schalter absolut.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.engine.effect_live as EL
from src.ui.virtualconsole.vc_stepper import VCStepper


def _app():
    return QApplication.instance() or QApplication([])


class _Spec:
    def __init__(self, key="runner_count", lo=1, hi=16, kind="int", options=()):
        self.key = key
        self.kind = kind
        self.min = lo
        self.max = hi
        self.options = options


def test_registered_and_offered_for_param():
    _app()
    from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
    assert WIDGET_REGISTRY.get("VCStepper") is VCStepper
    from src.ui.virtualconsole.vc_effect_meta import (
        widget_choices, WIDGET_TYPE_LABELS, ControlKind)

    class _Opt:
        def __init__(self, k, kind="", small=False):
            self.kind = k
            self.param_kind = kind
            self.param_small_int = small

    # Stepper wird „vom Widget" nur fuer GANZZAHLIGE Parameter angeboten (Zaehler),
    # nicht fuer float-Parameter oder die Intensitaet (float 0..1).
    assert "VCStepper" in widget_choices(_Opt(ControlKind.PARAM, "int", True))
    assert "VCStepper" in widget_choices(_Opt(ControlKind.PARAM, "int", False))
    assert "VCStepper" in widget_choices(_Opt(ControlKind.PARAM, "select"))
    assert "VCStepper" in widget_choices(_Opt(ControlKind.PARAM, "bool"))
    assert "VCStepper" not in widget_choices(_Opt(ControlKind.PARAM, "float"))
    assert "VCStepper" not in widget_choices(_Opt(ControlKind.INTENSITY))
    assert "VCStepper" in WIDGET_TYPE_LABELS


def test_step_by_sets_absolute_and_clamps():
    _app()
    orig = (EL.get_param, EL.set_param, EL.list_params)
    calls = []
    EL.list_params = lambda fid=None: [_Spec()]
    EL.set_param = lambda key, val, fid=None: (calls.append((key, val)), True)[1]
    try:
        s = VCStepper()
        s.param_key = "runner_count"
        s.function_id = None
        s.step = 1
        EL.get_param = lambda key, fid=None: 3
        s.step_by(1)
        assert calls[-1] == ("runner_count", 4)
        EL.get_param = lambda key, fid=None: 16
        s.step_by(1)
        assert calls[-1] == ("runner_count", 16)   # Obergrenze geklemmt
        EL.get_param = lambda key, fid=None: 1
        s.step_by(-1)
        assert calls[-1] == ("runner_count", 1)     # Untergrenze geklemmt
        # Schrittweite > 1
        s.step = 3
        EL.get_param = lambda key, fid=None: 5
        s.step_by(1)
        assert calls[-1] == ("runner_count", 8)
    finally:
        EL.get_param, EL.set_param, EL.list_params = orig


def test_step_by_cycles_select_and_toggles_bool():
    _app()
    orig = (EL.get_param, EL.set_param, EL.list_params)
    calls = []
    EL.set_param = lambda key, val, fid=None: (calls.append((key, val)), True)[1]
    try:
        stepper = VCStepper()
        stepper.param_key = "direction"
        EL.list_params = lambda fid=None: [
            _Spec("direction", kind="select", options=("forward", "reverse"))
        ]
        EL.get_param = lambda key, fid=None: "forward"
        stepper.step_by(1)
        assert calls[-1] == ("direction", "reverse")

        stepper.param_key = "pingpong"
        EL.list_params = lambda fid=None: [_Spec("pingpong", kind="bool")]
        EL.get_param = lambda key, fid=None: False
        stepper.step_by(1)
        assert calls[-1] == ("pingpong", True)
    finally:
        EL.get_param, EL.set_param, EL.list_params = orig


def test_serialization_roundtrip():
    _app()
    s = VCStepper()
    s.param_key = "runner_width"
    s.function_id = 7
    s.function_ids = [8, 9]
    s.step = 3
    s.midi_cc = 5
    s.midi_ch = 2
    s.edit_slot = "MH"
    d = s.to_dict()
    assert d["type"] == "VCStepper"
    s2 = VCStepper()
    s2.apply_dict(d)
    assert (s2.param_key, s2.function_id, s2.function_ids, s2.step,
            s2.midi_cc, s2.midi_ch, s2.edit_slot) == \
        ("runner_width", 7, [8, 9], 3, 5, 2, "MH")


def test_canvas_aspect_and_droppable():
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    c = VCCanvas()
    s = VCStepper()
    assert c._widget_aspect(s) == "param"
    assert VCStepper in c._droppable_types()
