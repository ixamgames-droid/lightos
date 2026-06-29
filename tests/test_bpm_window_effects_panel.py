"""Stufe 2 — BPM-Fenster „Effekte je Bus" (taktgleich-Panel) + Manager-Helfer.

Deckt ab:
- TempoBusManager.list_effects_by_bus: gruppiert zeitbasierte Effekte nach
  AUFGELOESTEM Bus (Aliase ""/Global/default -> ein Topf "default"), feste A-D werden
  erzeugt, Free-Run unter "", statische Scenes fallen raus.
- TempoBusManager.assign_effects_to_bus: setzt Bus + re-ankert nur die genannten fids
  (Chaser-Exklusivitaet gegen audio_triggered greift).
- BpmManagerView-Panel: baut auf, listet Effekte je Bus, Haken schreibt align_on_start,
  Bus-Dropdown verschiebt, Multiplikator schreibt tempo_multiplier, Sync re-ankert.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QCheckBox
import pytest

_app = QApplication.instance() or QApplication([])

from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager
from src.core.engine.function_manager import get_function_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.ui.views.bpm_manager_view import BpmManagerView


@pytest.fixture(autouse=True)
def _clean():
    reset_tempo_bus_manager()
    get_function_manager().from_dict({"functions": []})
    get_bpm_manager().set_locked(False)
    get_bpm_manager().reset()
    get_tempo_bus_manager().set_auto_sync(True)
    yield
    from src.core.show.show_file import reset_show
    reset_show()
    mgr = get_bpm_manager(); mgr.set_locked(False); mgr.reset()
    get_tempo_bus_manager().set_auto_sync(False)


# ── Manager: list_effects_by_bus ────────────────────────────────────────────────
def test_list_effects_by_bus_groups_and_aliases():
    tbm = get_tempo_bus_manager(); fm = get_function_manager()
    m_global = fm.new_rgb_matrix("G"); m_global.tempo_bus_id = "Global"
    m_alias = fm.new_rgb_matrix("A0"); m_alias.tempo_bus_id = ""        # zeitbasiert -> Default? nein: leer = Free-Run
    m_busa = fm.new_rgb_matrix("BA"); m_busa.tempo_bus_id = "A"
    ch_def = fm.new_chaser("CD"); ch_def.tempo_bus_id = "default"
    scene = fm.new_scene("S")                                          # statisch -> raus
    groups = tbm.list_effects_by_bus()
    # Global + default landen im selben Topf "default"
    assert m_global in groups.get("default", [])
    assert ch_def in groups.get("default", [])
    # Bus A getrennt
    assert m_busa in groups.get("A", [])
    # leere tempo_bus_id einer zeitbasierten Matrix = Free-Run-Bucket ""
    assert m_alias in groups.get("", [])
    # statische Scene taucht NICHT auf
    assert all(scene not in v for v in groups.values())
    # feste Buses A-D existieren jetzt (lazy erzeugt)
    for b in ("A", "B", "C", "D"):
        assert tbm.get(b) is not None


# ── Manager: assign_effects_to_bus ──────────────────────────────────────────────
def test_assign_effects_to_bus_sets_and_reanchors_only_targets():
    tbm = get_tempo_bus_manager(); fm = get_function_manager()
    a = fm.new_rgb_matrix("A"); a.tempo_bus_id = "Global"
    b = fm.new_rgb_matrix("B"); b.tempo_bus_id = "Global"
    b._beat_anchor = 99.0
    tbm.assign_effects_to_bus([a.id], "A")
    assert a.tempo_bus_id == "A", "Ziel-fid muss auf den neuen Bus zeigen"
    assert b.tempo_bus_id == "Global", "andere Effekte bleiben unberuehrt"
    assert b._beat_anchor == 99.0, "nicht-Ziel-Effekt darf nicht re-ankert werden"


def test_assign_chaser_to_bus_disables_audio_triggered():
    tbm = get_tempo_bus_manager(); fm = get_function_manager()
    c = fm.new_chaser("C"); c.audio_triggered = True
    tbm.assign_effects_to_bus([c.id], "B")
    assert c.tempo_bus_id == "B"
    assert c.audio_triggered is False


# ── View-Panel ──────────────────────────────────────────────────────────────────
def _row_checkbox(view, fid):
    tree = view._fx_tree
    from PySide6.QtCore import Qt
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        for j in range(top.childCount()):
            row = top.child(j)
            if row.data(0, Qt.ItemDataRole.UserRole) == fid:
                wrap = tree.itemWidget(row, 4)
                return wrap.findChild(QCheckBox) if wrap else None
    return None


def test_panel_builds_and_lists_effects():
    fm = get_function_manager()
    m = fm.new_rgb_matrix("M"); m.tempo_bus_id = "Global"
    view = BpmManagerView()
    view._refresh_effects_panel()
    assert view._fx_tree.topLevelItemCount() == 6   # Haupt-BPM + A-D + Frei
    top_main = view._fx_tree.topLevelItem(0)
    names = [top_main.child(k).text(0) for k in range(top_main.childCount())]
    assert "M" in names, "Global-Matrix muss unter Haupt-BPM stehen"


def test_panel_checkbox_writes_align_on_start():
    fm = get_function_manager()
    m = fm.new_rgb_matrix("M"); m.tempo_bus_id = "Global"
    assert m.align_on_start is True
    view = BpmManagerView()
    view._refresh_effects_panel()
    chk = _row_checkbox(view, m.id)
    assert chk is not None and chk.isChecked() is True
    chk.setChecked(False)                       # User entfernt den Haken
    assert m.align_on_start is False


def test_panel_bus_dropdown_moves_effect():
    fm = get_function_manager()
    m = fm.new_rgb_matrix("M"); m.tempo_bus_id = "Global"
    view = BpmManagerView()
    view._on_row_bus_changed(m.id, "C")         # Handler direkt (Dropdown-Wahl)
    assert m.tempo_bus_id == "C"


def test_panel_mult_handler_writes_multiplier():
    fm = get_function_manager()
    m = fm.new_rgb_matrix("M"); m.tempo_bus_id = "Global"
    view = BpmManagerView()
    view._on_row_mult_changed(m.id, 2.0)
    assert abs(m.tempo_multiplier - 2.0) < 1e-9


def test_panel_sync_now_reanchors_running_bus_effects():
    tbm = get_tempo_bus_manager(); fm = get_function_manager(); mgr = get_bpm_manager()
    mgr.set_manual_bpm(120.0)
    m = fm.new_rgb_matrix("M"); m.tempo_bus_id = "Global"; m.start()
    d = tbm.get("default")
    d.advance_frame(1.0)
    m._beat_anchor = 0.0                        # kuenstlich verstellt
    view = BpmManagerView()
    view._on_bus_sync_now("default")
    assert abs(m._beat_anchor - d.position()) < 1e-6, "Sync jetzt muss alle Bus-Effekte re-ankern"
