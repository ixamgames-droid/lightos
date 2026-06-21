"""F2 (Fade-Params), F5 (Freeze-Hold, gated auf is_frozen), F7 (Global-Bus),
F3 (neue Button-Aktionen + globaler Freeze) — neue Engine-Features fuer die
Farb-/Effekt-VC-Show. Reine Engine-Tests (kein Qt).
"""
from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm
from src.core.engine.chaser import Chaser


def _clean_bpm():
    from src.core.engine.bpm_manager import get_bpm_manager
    mgr = get_bpm_manager()
    mgr.set_locked(False)
    mgr.reset()


def _run_bus(bus, n=10, dt=0.05):
    for _ in range(n):
        bus.advance_frame(dt)


# ── F2: Fade-In/Out als Live-Param (nur RgbMatrix; EFX bewusst nicht) ──────────
def test_rgbmatrix_fade_params_exposed_and_settable():
    m = RgbMatrixInstance("m")
    keys = {p.key for p in m.list_params()}
    assert {"env_fade_in", "env_fade_out", "env_fade"} <= keys
    assert m.set_param("env_fade_in", 2.5) and abs(m.get_param("env_fade_in") - 2.5) < 1e-6
    assert abs(m.env_fade_in - 2.5) < 1e-6
    assert m.set_param("env_fade_out", 1.0) and abs(m.env_fade_out - 1.0) < 1e-6
    m.set_param("env_fade", 3.0)
    assert abs(m.env_fade_in - 3.0) < 1e-6 and abs(m.env_fade_out - 3.0) < 1e-6


def test_fade_param_clamped_nonnegative():
    m = RgbMatrixInstance("m")
    m.set_param("env_fade_in", -5.0)
    assert m.env_fade_in == 0.0


# ── F7: 'Global'-Bus-Alias + Dropdown-Option in allen drei Engines ────────────
def test_global_bus_alias_resolves_to_default():
    reset_tempo_bus_manager()
    tbm = get_tempo_bus_manager()
    d = tbm.get("default")
    assert tbm.get("Global") is d
    assert tbm.get("global") is d
    assert tbm.get("") is d


def test_global_option_in_all_engine_dropdowns():
    for inst in (RgbMatrixInstance("m"), EfxInstance("e"), Chaser("c")):
        spec = next(p for p in inst.list_params() if p.key == "tempo_bus_id")
        assert "Global" in spec.options, f"{type(inst).__name__}: {spec.options}"


# ── F5: Freeze-Hold (gated): hold NUR bei aktivem Freeze, sonst Free-Run ───────
def test_rgbmatrix_freerun_when_bus_idle_not_frozen():
    # Bus zugewiesen, aber bpm 0 OHNE Freeze -> Free-Run (rueckwaerts-kompatibel).
    reset_tempo_bus_manager()
    bus = get_tempo_bus_manager().ensure_bus("A")
    bus.set_role("master")
    bus.set_bpm(0.0)
    m = RgbMatrixInstance("m", cols=4, rows=1)
    m.algorithm = RgbAlgorithm.CHASE
    m.tempo_bus_id = "A"
    m.matrix_speed = 2.0
    m._advance_step(0.1); a = m._step
    m._advance_step(0.1); b = m._step
    assert b != a, "ohne Freeze soll ein nicht gestarteter Bus den Effekt frei laufen lassen"


def test_rgbmatrix_holds_on_freeze():
    reset_tempo_bus_manager()
    tbm = get_tempo_bus_manager()
    bus = tbm.ensure_bus("A"); bus.set_role("master"); bus.set_bpm(120.0)
    m = RgbMatrixInstance("m", cols=4, rows=1)
    m.algorithm = RgbAlgorithm.CHASE
    m.tempo_bus_id = "A"
    _run_bus(bus); m._advance_step(0.05); s1 = m._step
    _run_bus(bus, 5); m._advance_step(0.05); s2 = m._step
    assert s2 != s1, "laeuft nicht auf laufendem Bus"
    try:
        tbm.toggle_freeze()
        for _ in range(5):
            bus.advance_frame(0.05)
        m._advance_step(0.05); s3 = m._step
        m._advance_step(0.05); s4 = m._step
        assert s4 == s3, "kein Hold bei Freeze (Effekt laeuft im Free-Run weiter)"
    finally:
        if tbm.is_frozen():
            tbm.toggle_freeze()
        _clean_bpm()


def test_efx_holds_on_freeze():
    reset_tempo_bus_manager()
    tbm = get_tempo_bus_manager()
    bus = tbm.ensure_bus("A"); bus.set_role("master"); bus.set_bpm(120.0)
    e = EfxInstance("e")
    e.fixtures = [EfxFixture(fid=1)]
    e.algorithm = EfxAlgorithm.CIRCLE
    e.tempo_bus_id = "A"
    _run_bus(bus); e._advance(0.05); p1 = e._phase
    _run_bus(bus, 5); e._advance(0.05); p2 = e._phase
    assert p2 != p1, "EFX laeuft nicht auf laufendem Bus"
    try:
        tbm.toggle_freeze()
        e._advance(0.05); p3 = e._phase
        e._advance(0.05); p4 = e._phase
        assert p4 == p3, "EFX-Bewegung friert bei Freeze nicht ein"
    finally:
        if tbm.is_frozen():
            tbm.toggle_freeze()
        _clean_bpm()


def test_efx_freerun_when_no_bus_assigned():
    reset_tempo_bus_manager()
    e = EfxInstance("e")
    e.fixtures = [EfxFixture(fid=1)]
    e.algorithm = EfxAlgorithm.CIRCLE
    e.tempo_bus_id = ""        # frei
    e._advance(0.1); a = e._phase
    e._advance(0.1); b = e._phase
    assert a != b, "Free-Run sollte ohne Bus weiterlaufen"


# ── F3: neue Button-Aktionen + globaler Freeze-Toggle ─────────────────────────
def test_new_button_actions_and_labels():
    from src.ui.virtualconsole.vc_button import ButtonAction, BUTTON_ACTION_LABELS
    assert ButtonAction.ALL_WHITE and ButtonAction.FREEZE and ButtonAction.STOP_EFFECTS
    labelled = {a for a, _ in BUTTON_ACTION_LABELS}
    assert {ButtonAction.ALL_WHITE, ButtonAction.FREEZE, ButtonAction.STOP_EFFECTS} <= labelled


def test_toggle_freeze_zeros_and_restores():
    from src.core.engine.bpm_manager import get_bpm_manager
    reset_tempo_bus_manager()
    tbm = get_tempo_bus_manager()
    a = tbm.ensure_bus("A"); a.set_role("master"); a.set_bpm(150.0)
    mgr = get_bpm_manager()
    try:
        mgr.set_manual_bpm(128.0)
        assert not tbm.is_frozen()
        assert tbm.toggle_freeze() is True
        assert tbm.is_frozen()
        assert a.bpm == 0.0, "Bus A nicht eingefroren"
        assert mgr.bpm == 0.0, "globaler Leader nicht eingefroren"
        assert tbm.toggle_freeze() is False
        assert not tbm.is_frozen()
        assert a.bpm == 150.0, "Bus A nicht wiederhergestellt"
        assert mgr.bpm == 128.0, "globaler Leader nicht wiederhergestellt"
    finally:
        _clean_bpm()
