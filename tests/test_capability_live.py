"""Phase 3: bindungs-bewusste Live-Checks + Render-Smoke.

- Live-Checks: ein param_key, der für die GEBUNDENE Funktion/Algo nicht existiert
  (global aber schon), und eine Effekt-Aktion am falschen Funktionstyp werden
  gefangen — das schafft der statische Check nicht (er kennt die Bindung nicht).
- Render-Smoke: der echte Renderer erzeugt für einen geladenen Effekt echtes DMX.
"""
from __future__ import annotations

import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fixture_db_seeded() -> bool:
    try:
        from src.core.database.fixture_db import get_all_manufacturers
        return bool(get_all_manufacturers())
    except Exception:
        return False


def test_live_checks_catch_inert_param_and_wrong_action():
    """ACCEPTANCE Phase 3: gültig-aber-inerter param_key + falsche Effekt-Aktion."""
    from src.core.show.show_file import reset_show
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine.rgb_matrix import RgbAlgorithm
    from src.core.app_state import get_state
    from src.core.capability.validate import validate_show_live, ERROR, format_findings

    reset_show()
    state = get_state()
    fm = get_function_manager()
    m = fm.new_rgb_matrix("Test Matrix")
    m.algorithm = RgbAlgorithm.PLAIN   # PLAIN kennt KEIN runner_count (das hat CHASE)

    state._vc_layout = {"widgets": [
        # gültiger param_key global (CHASE), aber an einer PLAIN-Matrix inert
        {"type": "VCSlider", "caption": "x", "mode": "EffectParam",
         "param_key": "runner_count", "function_id": m.id},
        # capture_step ist eine Chaser-Aktion, keine Matrix-Aktion
        {"type": "VCButton", "caption": "y", "action": "EffectAction",
         "effect_action_key": "capture_step", "function_id": m.id},
    ]}

    findings = validate_show_live(state)
    codes = [f.code for f in findings if f.severity == ERROR]
    assert "VC-PARAMKEY-LIVE" in codes, format_findings(findings)
    assert "VC-ACTION-LIVE" in codes, format_findings(findings)


def test_live_checks_pass_for_valid_binding():
    """Ein gültiger param_key für den gebundenen Algo wird NICHT gemeldet."""
    from src.core.show.show_file import reset_show
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine.rgb_matrix import RgbAlgorithm
    from src.core.app_state import get_state
    from src.core.capability.validate import validate_show_live, ERROR

    reset_show()
    state = get_state()
    fm = get_function_manager()
    m = fm.new_rgb_matrix("Chase Matrix")
    m.algorithm = RgbAlgorithm.CHASE   # CHASE HAT runner_count
    state._vc_layout = {"widgets": [
        {"type": "VCSlider", "caption": "x", "mode": "EffectParam",
         "param_key": "runner_count", "function_id": m.id},
        {"type": "VCSlider", "caption": "s", "mode": "EffectSpeed",
         "param_key": "speed", "function_id": m.id},
    ]}
    errs = [f for f in validate_show_live(state) if f.severity == ERROR]
    assert not errs, [str(f) for f in errs]


def test_render_probe_demo_show():
    """Render-Smoke: ein Effekt der echten Demo-Show erzeugt echtes DMX."""
    if not _fixture_db_seeded():
        pytest.skip("Fixture-DB nicht geseedet — Render-Smoke übersprungen")
    path = os.path.join(_ROOT, "shows", "Demo_Show_Full.lshow")
    if not os.path.exists(path):
        pytest.skip("Demo_Show_Full.lshow fehlt")

    from src.core.show.show_file import load_show
    ok, msg = load_show(path)
    if not ok:
        pytest.skip(f"Show lädt nicht: {msg}")

    from src.core.engine.function_manager import get_function_manager
    from src.core.app_state import get_state
    from src.core.capability.render_probe import render_diff

    state = get_state()
    fm = get_function_manager()
    byname = {f.name: f for f in fm.all()}
    target = byname.get("PAR Dimmer Voll") or (fm.all()[0] if fm.all() else None)
    if target is None:
        pytest.skip("keine Funktion zum Testen")

    lit, moved, changed = render_diff(state, [target.id], channels=range(1, 131))
    assert lit or moved, (
        f"render_probe: '{target.name}' erzeugt kein DMX (lit={lit}, moved={moved})")


def test_render_probe_detects_inert():
    """Eine leere Szene (setzt nichts) wird als inert erkannt."""
    from src.core.show.show_file import reset_show
    from src.core.engine.function_manager import get_function_manager
    from src.core.app_state import get_state
    from src.core.capability.render_probe import assert_not_inert, InertEffectError

    reset_show()
    state = get_state()
    fm = get_function_manager()
    empty = fm.new_scene("Leere Szene")   # keine Werte gesetzt -> kein DMX
    with pytest.raises(InertEffectError):
        assert_not_inert(state, empty.id, channels=range(1, 64), frames=10)
