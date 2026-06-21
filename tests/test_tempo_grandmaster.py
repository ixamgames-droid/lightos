"""Unit-Tests fuer den Grand-Master-Override der Tempo-Buses (Phase B).

Siehe docs/SPEED_MASTER_SUB_PLAN.md. Ist der Grand-Master "scharf" (armed) und gesetzt
(bpm > 0), laeuft JEDER Master-Bus auf seinem Takt — die eigene Quelle wird uebertrumpft,
aber NICHT ueberschrieben (beim Entschaerfen kehrt die eigene BPM zurueck). Sub-Buses
bleiben relativ ueber ihren Parent (Grand × Faktor). Alles deterministisch via advance_frame.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

import src.core.engine.tempo_bus as tb
from src.core.engine.tempo_bus import (
    TempoBus,
    TempoBusManager,
    get_tempo_bus_manager,
    reset_tempo_bus_manager,
)
from src.core.engine.bpm_manager import get_bpm_manager


@pytest.fixture(autouse=True)
def _isolate_tempo_state():
    reset_tempo_bus_manager()
    get_bpm_manager().reset()
    yield
    reset_tempo_bus_manager()
    get_bpm_manager().reset()


# ── 1: Scharf → alle Master folgen dem Grand-Master ──────────────────────────────

def test_armed_grandmaster_overrides_all_masters():
    mgr = get_tempo_bus_manager()
    m1 = mgr.ensure_bus("M1")
    m1.set_bpm(120)
    m2 = mgr.ensure_bus("M2")
    m2.set_bpm(60)
    mgr.set_grandmaster_bpm(180)
    mgr.set_grandmaster_armed(True)
    assert m1.bpm == pytest.approx(180.0)
    assert m2.bpm == pytest.approx(180.0)
    for _ in range(10):
        mgr.advance_frame(0.1)          # 1.0s @180 -> 3 Beats
    assert m1.position() == pytest.approx(3.0, abs=1e-9)
    assert m2.position() == pytest.approx(3.0, abs=1e-9)


def test_disarm_returns_masters_to_own_bpm():
    mgr = get_tempo_bus_manager()
    m1 = mgr.ensure_bus("M1")
    m1.set_bpm(120)
    m2 = mgr.ensure_bus("M2")
    m2.set_bpm(60)
    mgr.set_grandmaster_bpm(180)
    mgr.set_grandmaster_armed(True)
    mgr.advance_frame(0.1)
    mgr.set_grandmaster_armed(False)
    assert m1.bpm == pytest.approx(120.0)   # eigene BPM kehrt zurueck
    assert m2.bpm == pytest.approx(60.0)


# ── 2: Subs bleiben relativ unter dem Grand-Master ───────────────────────────────

def test_sub_stays_relative_under_grandmaster():
    mgr = get_tempo_bus_manager()
    m = mgr.ensure_bus("M")
    m.set_bpm(100)
    s = mgr.ensure_bus("S")
    s.set_role("sub")
    s.set_parent("M")
    s.set_bus_multiplier(0.5)
    mgr.set_grandmaster_bpm(200)
    mgr.set_grandmaster_armed(True)
    assert m.bpm == pytest.approx(200.0)
    assert s.bpm == pytest.approx(100.0)        # 200 x 0.5
    for _ in range(10):
        mgr.advance_frame(0.1)                  # 1.0s @200 -> 200/60 Beats
    assert m.position() == pytest.approx(200.0 / 60.0, abs=1e-9)
    assert s.position() == pytest.approx(m.position() * 0.5, abs=1e-9)


# ── 3: Scharf, aber ungesetzt (bpm 0) → keine Wirkung ────────────────────────────

def test_armed_without_bpm_has_no_effect():
    mgr = get_tempo_bus_manager()
    m = mgr.ensure_bus("M")
    m.set_bpm(120)
    mgr.set_grandmaster_armed(True)             # grandmaster_bpm bleibt 0
    assert m.bpm == pytest.approx(120.0)
    for _ in range(10):
        mgr.advance_frame(0.1)
    assert m.position() == pytest.approx(2.0, abs=1e-9)   # eigener 120-Takt


# ── 4: Grand-Master uebertrumpft auch den Default/bpm_global-Bus ─────────────────

def test_grandmaster_overrides_default_bus():
    mgr = get_tempo_bus_manager()
    default = mgr.get(TempoBusManager.DEFAULT_BUS)
    assert default is not None
    mgr.set_grandmaster_bpm(150)
    mgr.set_grandmaster_armed(True)
    assert default.bpm == pytest.approx(150.0)
    for _ in range(10):
        mgr.advance_frame(0.1)                  # 1.0s @150 -> 2.5 Beats
    assert default.position() == pytest.approx(150.0 / 60.0, abs=1e-9)


# ── 5: Tap + Zahlenfeld + Clamp ──────────────────────────────────────────────────

def test_tap_grandmaster_math(monkeypatch):
    times = [10.0, 10.5, 11.0, 11.5]
    state = {"i": 0}

    def fake_monotonic():
        v = times[min(state["i"], len(times) - 1)]
        state["i"] += 1
        return v

    monkeypatch.setattr(tb.time, "monotonic", fake_monotonic)
    mgr = get_tempo_bus_manager()
    for _ in range(4):
        mgr.tap_grandmaster()                   # 0.5s Intervalle -> 120 BPM
    assert mgr.grandmaster_bpm == pytest.approx(120.0)


def test_set_grandmaster_bpm_clamps():
    mgr = get_tempo_bus_manager()
    mgr.set_grandmaster_bpm(5)                   # unter MIN -> 20
    assert mgr.grandmaster_bpm == pytest.approx(TempoBus.MIN_BPM)
    mgr.set_grandmaster_bpm(5000)               # ueber MAX -> 999
    assert mgr.grandmaster_bpm == pytest.approx(TempoBus.MAX_BPM)
    mgr.set_grandmaster_bpm(0)                   # 0 = aus
    assert mgr.grandmaster_bpm == 0.0


def test_grandmaster_default_off():
    mgr = get_tempo_bus_manager()
    assert mgr.grandmaster_armed is False
    assert mgr.grandmaster_bpm == 0.0


def test_grandmaster_persistence_roundtrip():
    mgr = get_tempo_bus_manager()
    mgr.set_grandmaster_bpm(140)
    mgr.set_grandmaster_armed(True)
    d = mgr.grandmaster_to_dict()
    assert d["armed"] is True
    assert d["bpm"] == pytest.approx(140.0)

    # Frischer Manager -> Default aus; dann laden -> Zustand wieder da.
    reset_tempo_bus_manager()
    get_bpm_manager().reset()
    mgr2 = get_tempo_bus_manager()
    assert mgr2.grandmaster_armed is False
    mgr2.load_grandmaster(d)
    assert mgr2.grandmaster_armed is True
    assert mgr2.grandmaster_bpm == pytest.approx(140.0)

    # Leeres dict = Reset (neue Show kommt nie im Override-Modus hoch).
    mgr2.load_grandmaster({})
    assert mgr2.grandmaster_armed is False
    assert mgr2.grandmaster_bpm == 0.0
