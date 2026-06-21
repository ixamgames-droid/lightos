"""Unit-Tests fuer die Master/Sub-Hierarchie der Tempo-Buses (Phase A).

Siehe docs/SPEED_MASTER_SUB_PLAN.md. Ein Sub-Bus folgt einem Master mit einem
Faktor (``bus_multiplier``): seine Position/BPM wird beim Lesen aus dem Parent
abgeleitet (parent.position() x mult), ueber einen Anker stetig gehalten. Alles
deterministisch ueber ``advance_frame`` getrieben — keine sleeps, kein Daemon-Thread.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

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


def _make_master_sub(mult: float, master_bpm: float = 120.0):
    """Master 'M' (manual) + Sub 'S' (folgt M x mult). Liefert (mgr, M, S)."""
    mgr = get_tempo_bus_manager()
    m = mgr.ensure_bus("M")
    m.set_bpm(master_bpm)
    s = mgr.ensure_bus("S")
    s.set_role("sub")
    assert s.set_parent("M") is True
    s.set_bus_multiplier(mult)
    return mgr, m, s


# ── 1: Sub folgt Master mit Faktor (Position + BPM) ──────────────────────────────

def test_sub_half_speed_position_and_bpm():
    mgr, m, s = _make_master_sub(0.5)
    for _ in range(10):
        mgr.advance_frame(0.1)          # 1.0s @120 BPM -> Master 2 Beats
    assert m.position() == pytest.approx(2.0, abs=1e-9)
    assert s.position() == pytest.approx(1.0, abs=1e-9)   # halb so schnell
    assert s.bpm == pytest.approx(60.0)                   # 120 x 0.5


def test_sub_double_speed_is_phase_coupled():
    mgr, m, s = _make_master_sub(2.0)
    for _ in range(10):
        mgr.advance_frame(0.1)          # Master 2 Beats
    assert s.position() == pytest.approx(4.0, abs=1e-9)   # 2x
    assert s.bpm == pytest.approx(240.0)
    # Phasen-Kopplung: bei JEDEM ganzen Master-Beat ist die Sub-Position ganzzahlig.
    reset_tempo_bus_manager()
    get_bpm_manager().reset()
    mgr, m, s = _make_master_sub(2.0)
    for _ in range(20):
        mgr.advance_frame(0.05)         # feine Schritte
        mp = m.position()
        if abs(mp - round(mp)) < 1e-9 and mp > 0:
            assert abs(s.position() - round(s.position())) < 1e-9


# ── 2: Master-BPM-Aenderung zieht den Sub mit ────────────────────────────────────

def test_master_bpm_change_drives_sub():
    mgr, m, s = _make_master_sub(0.5)
    assert s.bpm == pytest.approx(60.0)
    m.set_bpm(100)
    assert s.bpm == pytest.approx(50.0)                   # 100 x 0.5
    for _ in range(10):
        mgr.advance_frame(0.1)          # 1.0s @100 -> Master ~1.667 Beats
    assert s.position() == pytest.approx(m.position() * 0.5, abs=1e-9)


# ── 3: Multiplier-Wechsel ist stetig (kein Positions-Sprung) ─────────────────────

def test_multiplier_change_is_continuous():
    mgr = get_tempo_bus_manager()
    m = mgr.ensure_bus("M")
    m.set_bpm(120)
    s = mgr.ensure_bus("S")
    s.set_role("sub")
    s.set_parent("M")
    s.set_bus_multiplier(1.0)
    for _ in range(5):
        mgr.advance_frame(0.1)          # 0.5s -> Master 1.0 Beat, Sub 1.0
    assert s.position() == pytest.approx(1.0, abs=1e-9)
    before = s.position()
    s.set_bus_multiplier(2.0)
    # Direkt nach dem Umschalten darf die Position NICHT springen.
    assert s.position() == pytest.approx(before, abs=1e-9)
    for _ in range(5):
        mgr.advance_frame(0.1)          # weitere 0.5s -> Master +1.0 Beat
    # ab jetzt doppelte Rate: 1.0 + (2.0 - 1.0) * 2 = 3.0
    assert m.position() == pytest.approx(2.0, abs=1e-9)
    assert s.position() == pytest.approx(3.0, abs=1e-9)


# ── 4: Zyklus-Schutz ─────────────────────────────────────────────────────────────

def test_cycle_is_rejected():
    mgr = get_tempo_bus_manager()
    a = mgr.ensure_bus("A")
    a.set_role("sub")
    b = mgr.ensure_bus("B")
    b.set_role("sub")
    assert b.set_parent("A") is True            # B folgt A
    assert a.set_parent("B") is False           # A->B->A waere ein Ring
    assert a.parent_id != "B"


def test_self_parent_is_rejected():
    mgr = get_tempo_bus_manager()
    a = mgr.ensure_bus("A")
    a.set_role("sub")
    assert a.set_parent("A") is False


# ── 5: Rollenwechsel ─────────────────────────────────────────────────────────────

def test_sub_to_master_takes_over_rate_and_continues():
    mgr, m, s = _make_master_sub(0.5)
    for _ in range(10):
        mgr.advance_frame(0.1)          # Master 2.0, Sub 1.0 @ 60 BPM
    assert s.position() == pytest.approx(1.0, abs=1e-9)
    pos_before = s.position()
    s.set_role("master")
    assert s.role == "master"
    assert s.bpm == pytest.approx(60.0)         # abgeleitete Rate uebernommen
    # Jetzt eigenstaendig: 60 BPM = 1 Beat/s, unabhaengig vom Master.
    mgr.advance_frame(1.0)
    assert s.position() == pytest.approx(pos_before + 1.0, abs=1e-6)


def test_master_to_sub_is_continuous():
    mgr = get_tempo_bus_manager()
    m = mgr.ensure_bus("M")
    m.set_bpm(120)
    x = mgr.ensure_bus("X")             # startet als Master
    x.set_bpm(120)
    mgr.advance_frame(1.0)              # beide 2.0 Beats
    assert x.position() == pytest.approx(2.0, abs=1e-9)
    x.set_role("sub")
    x.set_parent("M")                   # mult bleibt 1.0
    # Stetig: keine Sprung-Position beim Rollenwechsel.
    assert x.position() == pytest.approx(2.0, abs=1e-9)
    mgr.advance_frame(1.0)              # Master +2.0
    assert x.position() == pytest.approx(4.0, abs=1e-9)   # folgt jetzt mit x1


# ── 6: snapshot() eines Subs ist konsistent ──────────────────────────────────────

def test_sub_snapshot_consistency():
    mgr, m, s = _make_master_sub(0.5)
    mgr.advance_frame(0.3)              # 0.3s @120 -> Master 0.6, Sub 0.3
    bpm, count, phase, pos = s.snapshot()
    assert bpm == pytest.approx(60.0)
    assert count == 0
    assert phase == pytest.approx(0.3, abs=1e-9)
    assert pos == pytest.approx(0.3, abs=1e-9)


# ── 7: Persistenz ────────────────────────────────────────────────────────────────

def test_plain_master_dict_has_no_hierarchy_keys():
    """Rueckwaertskompatibel: ein gewoehnlicher Master serialisiert wie bisher."""
    m = TempoBus("M", source="manual")
    m.set_bpm(120)
    d = m.to_dict()
    assert d == {"bus_id": "M", "source": "manual", "bpm": pytest.approx(120.0)}
    assert "role" not in d and "parent_id" not in d and "bus_multiplier" not in d


def test_sub_dict_round_trip():
    s = TempoBus("S")
    s.role = "sub"
    s.parent_id = "M"
    s.bus_multiplier = 0.25
    d = s.to_dict()
    assert d["role"] == "sub"
    assert d["parent_id"] == "M"
    assert d["bus_multiplier"] == pytest.approx(0.25)
    r = TempoBus.from_dict(d)
    assert r.role == "sub"
    assert r.parent_id == "M"
    assert r.bus_multiplier == pytest.approx(0.25)


def test_from_dict_defaults_for_legacy_entry():
    """Alt-Eintrag ohne Hierarchie-Keys -> Default Master, parent '', mult 1.0."""
    r = TempoBus.from_dict({"bus_id": "Z", "source": "manual", "bpm": 100})
    assert r.role == "master"
    assert r.parent_id == ""
    assert r.bus_multiplier == pytest.approx(1.0)


def test_load_dict_restores_hierarchy_and_follows():
    mgr, m, s = _make_master_sub(0.5)
    data = mgr.to_dict()
    assert {d["bus_id"] for d in data} == {"M", "S"}

    reset_tempo_bus_manager()
    get_bpm_manager().reset()
    mgr2 = get_tempo_bus_manager()
    mgr2.load_dict(data)
    s2 = mgr2.get("S")
    m2 = mgr2.get("M")
    assert s2 is not None and m2 is not None
    assert s2.role == "sub"
    assert s2.parent_id == "M"
    assert s2.bus_multiplier == pytest.approx(0.5)
    assert m2.bpm == pytest.approx(120.0)               # Master-BPM persistiert
    for _ in range(10):
        mgr2.advance_frame(0.1)
    assert m2.position() == pytest.approx(2.0, abs=1e-9)
    assert s2.position() == pytest.approx(1.0, abs=1e-9)


def test_master_buses_excludes_default_and_subs():
    mgr = get_tempo_bus_manager()
    mgr.ensure_bus("M").set_bpm(120)
    s = mgr.ensure_bus("S")
    s.set_role("sub")
    ids = {b.bus_id for b in mgr.master_buses()}
    assert ids == {"M"}
    assert TempoBusManager.DEFAULT_BUS not in ids
