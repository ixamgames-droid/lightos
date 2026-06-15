"""F-5: Fade-Kurve pro Cue.

Stellt sicher, dass jede Cue einen waehlbaren Fade-Verlauf traegt, alte Shows
ohne das Feld bit-identisch wie frueher faden (Default ``scurve`` = Smoothstep)
und der CueStack die Kurve der Cue an den laufenden Fade durchreicht.
"""
from src.core.engine.cue import Cue
from src.core.engine.cue_stack import CueStack, FadeState
from src.core.engine import fade_curve


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


# ── Modell / Persistenz ─────────────────────────────────────────────────────────

def test_cue_default_curve_is_scurve():
    assert Cue(number=1.0).fade_curve == "scurve"


def test_cue_from_dict_legacy_defaults_scurve():
    # Alt-Show: Cue-Dict ohne fade_curve-Feld
    c = Cue.from_dict({"number": 2.0, "fade_in": 1.0})
    assert c.fade_curve == "scurve"


def test_cue_roundtrip_preserves_curve():
    c = Cue(number=3.0, fade_curve="ease_in")
    assert Cue.from_dict(c.to_dict()).fade_curve == "ease_in"


def test_cuestack_roundtrip_preserves_curve():
    stack = CueStack("T")
    stack.add_cue(Cue(number=1.0, fade_curve="snap"))
    stack.add_cue(Cue(number=2.0, fade_curve="linear"))
    rt = CueStack.from_dict(stack.to_dict())
    assert [c.fade_curve for c in rt.cues] == ["snap", "linear"]


# ── Verlauf-Resolver ────────────────────────────────────────────────────────────

def test_eval_named_endpoints_all_curves():
    for name in fade_curve.CURVE_NAMES:
        assert abs(fade_curve.eval_named(name, 0.0)) < 1e-6
        assert abs(fade_curve.eval_named(name, 1.0) - 1.0) < 1e-6


def test_eval_named_unknown_falls_back_to_smoothstep():
    assert abs(fade_curve.eval_named("bogus", 0.5) - _smoothstep(0.5)) < 1e-9


def test_scurve_matches_legacy_smoothstep():
    for p in (0.1, 0.25, 0.5, 0.75, 0.9):
        assert abs(fade_curve.eval_named("scurve", p) - _smoothstep(p)) < 1e-9


def test_linear_curve_is_linear():
    for p in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert abs(fade_curve.eval_named("linear", p) - p) < 1e-9


def test_snap_holds_then_jumps():
    assert fade_curve.eval_named("snap", 0.5) < 0.01     # haelt am Anfang
    assert fade_curve.eval_named("snap", 1.0) == 1.0     # springt am Ende


def test_curve_labels_cover_all_names():
    for name in fade_curve.CURVE_NAMES:
        assert name in fade_curve.CURVE_LABELS


# ── FadeState wendet die Kurve an ────────────────────────────────────────────────

def test_fadestate_applies_linear_curve():
    fs = FadeState({1: {"intensity": 0}}, {1: {"intensity": 200}}, 2.0, 0.0, "linear")
    fs.manual = True
    fs.manual_pos = 0.5
    assert fs.current_values()[1]["intensity"] == 100   # linear 0->200 @0.5


def test_fadestate_default_is_backward_compatible():
    # Ohne curve-Arg == altes festes Smoothstep-Verhalten
    fs = FadeState({1: {"x": 0}}, {1: {"x": 255}}, 1.0, 0.0)
    assert fs.curve == "scurve"
    fs.manual = True
    fs.manual_pos = 0.3
    assert fs.current_values()[1]["x"] == int(255 * _smoothstep(0.3))


def test_fadestate_done_returns_targets_exactly():
    fs = FadeState({1: {"x": 0}}, {1: {"x": 255}}, 1.0, 0.0, "ease_in")
    fs.manual = True
    fs.manual_pos = 1.0
    assert fs.current_values()[1]["x"] == 255
    assert fs.done is True


# ── CueStack reicht die Kurve durch ──────────────────────────────────────────────

def test_cuestack_go_uses_cue_curve():
    stack = CueStack("T")
    stack.add_cue(Cue(number=1.0, fade_in=1.0, values={1: {"intensity": 0}}))
    stack.add_cue(Cue(number=2.0, fade_in=2.0, fade_curve="linear",
                      values={1: {"intensity": 100}}))
    stack.go()    # -> Cue 1 (scurve)
    assert stack._fade is not None and stack._fade.curve == "scurve"
    stack.go()    # -> Cue 2 (linear)
    assert stack._fade is not None and stack._fade.curve == "linear"
