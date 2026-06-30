"""Phase D2: Tempo-Speeds & Grand-Master-Panel im BPM-Manager-Tab.

Headless (offscreen Qt). Das Panel mutiert ausschliesslich den TempoBusManager;
hier wird ueber die echten Widgets gefahren und der Manager-Zustand geprueft.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from PySide6.QtWidgets import QApplication

from src.core.engine.tempo_bus import (
    get_tempo_bus_manager, reset_tempo_bus_manager, TempoBusManager,
)
from src.core.engine.bpm_manager import get_bpm_manager


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def _isolated_prefs(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


@pytest.fixture
def _clean_tempo():
    reset_tempo_bus_manager()
    get_bpm_manager().reset()
    yield
    reset_tempo_bus_manager()
    get_bpm_manager().reset()


def _row_for(view, busid: str) -> int:
    t = view._bus_table
    for r in range(t.rowCount()):
        it = t.item(r, 0)
        if it is None:
            continue
        if busid == TempoBusManager.DEFAULT_BUS and it.text().startswith("Default"):
            return r
        if it.text() == busid:
            return r
    return -1


def _make_view(qapp):
    from src.ui.views.bpm_manager_view import BpmManagerView
    v = BpmManagerView()
    qapp.processEvents()
    return v


def test_table_lists_default_bus(qapp, _isolated_prefs, _clean_tempo):
    v = _make_view(qapp)
    assert v._bus_table.rowCount() >= 1
    assert _row_for(v, TempoBusManager.DEFAULT_BUS) >= 0
    v.deleteLater(); qapp.processEvents()


def test_grandmaster_controls_drive_manager(qapp, _isolated_prefs, _clean_tempo):
    v = _make_view(qapp)
    mgr = get_tempo_bus_manager()
    v._gm_bpm.setValue(140)                  # -> _on_gm_bpm
    assert mgr.grandmaster_bpm == pytest.approx(140.0)
    v._gm_arm.setChecked(True)               # -> _on_gm_arm
    assert mgr.grandmaster_armed is True
    v._gm_arm.setChecked(False)
    assert mgr.grandmaster_armed is False
    v.deleteLater(); qapp.processEvents()


def test_create_named_master(qapp, _isolated_prefs, _clean_tempo):
    v = _make_view(qapp)
    mgr = get_tempo_bus_manager()
    v._new_master_name.setText("Bass")
    v._on_add_master()
    bus = mgr.get("Bass")
    assert bus is not None
    assert bus.role == "master"
    assert _row_for(v, "Bass") >= 0
    v.deleteLater(); qapp.processEvents()


def test_edit_bus_to_sub(qapp, _isolated_prefs, _clean_tempo):
    v = _make_view(qapp)
    mgr = get_tempo_bus_manager()
    v._new_master_name.setText("Bass")
    v._on_add_master()
    row = _row_for(v, "Bass")
    assert row >= 0
    v._bus_table.selectRow(row)
    qapp.processEvents()
    # Rolle -> Sub, Parent -> Default, Faktor -> 1/2
    v._edit_role.setCurrentIndex(1)          # "sub"
    pidx = v._edit_parent.findData("")
    v._edit_parent.setCurrentIndex(pidx)
    fidx = v._edit_factor.findData(0.5)
    v._edit_factor.setCurrentIndex(fidx)
    v._on_apply_bus_edit()
    bus = mgr.get("Bass")
    assert bus is not None
    assert bus.role == "sub"
    assert bus.parent_id == ""
    assert bus.bus_multiplier == pytest.approx(0.5)
    v.deleteLater(); qapp.processEvents()


def test_delete_named_bus(qapp, _isolated_prefs, _clean_tempo):
    v = _make_view(qapp)
    mgr = get_tempo_bus_manager()
    mgr.ensure_bus("Temp").set_role("master")
    v._refresh_speeds()
    row = _row_for(v, "Temp")
    assert row >= 0
    v._bus_table.selectRow(row)
    qapp.processEvents()
    v._on_delete_bus()
    assert mgr.get("Temp") is None
    v.deleteLater(); qapp.processEvents()


def test_cannot_delete_default(qapp, _isolated_prefs, _clean_tempo):
    v = _make_view(qapp)
    mgr = get_tempo_bus_manager()
    row = _row_for(v, TempoBusManager.DEFAULT_BUS)
    v._bus_table.selectRow(row)
    qapp.processEvents()
    v._on_delete_bus()                       # darf den Default nicht entfernen
    assert mgr.get(TempoBusManager.DEFAULT_BUS) is not None
    v.deleteLater(); qapp.processEvents()


def _bpm_cell(view, busid: str) -> str:
    r = _row_for(view, busid)
    if r < 0:
        return ""
    it = view._bus_table.item(r, 4)          # Spalte "BPM"
    return it.text() if it is not None else ""


def test_bpm_column_follows_sound_bpm_live(qapp, _isolated_prefs, _clean_tempo):
    """Regression: Ändert sich die Sound-BPM (Leader), zieht die BPM-Spalte der
    Bus-Tabelle live nach (über den Poll-Refresh). Vorher blieb sie bis zum
    nächsten vollen Refresh stehen — der eigentliche Bug-Report."""
    mgr = get_tempo_bus_manager()
    leader = get_bpm_manager()
    # Bus A als Sub, der der Sound-BPM (Default) folgt.
    a = mgr.ensure_bus("A")
    a.set_role("sub")
    a.set_parent("")                         # "" → Default/Sound-BPM
    a.set_bus_multiplier(1.0)
    # Anfangs-Sound-BPM setzen + in den Default-Bus integrieren (Render-Tick).
    leader.request_bpm(120.0, "audio")
    mgr.advance_frame(0.05)

    v = _make_view(qapp)
    assert _bpm_cell(v, TempoBusManager.DEFAULT_BUS) == "120"
    assert _bpm_cell(v, "A") == "120"

    # Sound-BPM ändert sich live — ohne ein UI-Event auszulösen.
    leader.request_bpm(150.0, "audio")
    mgr.advance_frame(0.05)
    v._refresh_bus_bpm_live()                # Poll-Tick simulieren (statt 150 ms warten)
    assert _bpm_cell(v, TempoBusManager.DEFAULT_BUS) == "150"
    assert _bpm_cell(v, "A") == "150"
    v.deleteLater(); qapp.processEvents()


def test_bpm_live_refresh_rebuilds_on_bus_count_change(qapp, _isolated_prefs, _clean_tempo):
    """Kommt zwischen zwei Polls ein Bus dazu, baut der Live-Refresh die Tabelle
    einmal voll neu auf (Zeilenanzahl ≠ Busanzahl → _refresh_speeds)."""
    mgr = get_tempo_bus_manager()
    v = _make_view(qapp)
    assert _row_for(v, "Bass") < 0              # noch nicht in der Tabelle
    mgr.ensure_bus("Bass").set_role("master")   # ohne UI → Tabelle noch nicht informiert
    v._refresh_bus_bpm_live()                   # Zeilen ≠ Buses → voller Rebuild
    assert v._bus_table.rowCount() == len(mgr.all_buses())
    assert _row_for(v, "Bass") >= 0
    v.deleteLater(); qapp.processEvents()
