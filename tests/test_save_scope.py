"""Cluster D / F1: gruppen-gescopter Save.

Speichern (Snap/Szene) darf nur Geraete im aktiven Scope (= aktuelle Auswahl /
aktive Gruppe) beruecksichtigen, nicht liegengebliebene Programmer-Werte zuvor
gewaehlter Gruppen.
"""
from PySide6.QtWidgets import QApplication

from src.ui.views.snap_file_panel import ChannelSelectDialog


def _app():
    return QApplication.instance() or QApplication([])


def test_dialog_scopes_to_fids():
    _app()
    prog = {
        1: {"color_r": 255, "dimmer": 200},   # Gruppe A - NICHT im Scope
        2: {"color_g": 128},                  # Gruppe A - NICHT im Scope
        3: {"color_b": 255, "dimmer": 100},   # Gruppe B - im Scope
        4: {"intensity": 255},                # Gruppe B - im Scope
    }
    dlg = ChannelSelectDialog(prog, scope_fids=[3, 4])
    out = dlg.filter_programmer(prog)
    assert set(out.keys()) == {3, 4}
    assert 1 not in out and 2 not in out


def test_dialog_no_scope_keeps_all():
    _app()
    prog = {1: {"color_r": 255}, 2: {"dimmer": 100}}
    dlg = ChannelSelectDialog(prog)  # kein Scope -> Alt-Verhalten
    out = dlg.filter_programmer(prog)
    assert set(out.keys()) == {1, 2}


def test_dialog_attr_group_filter_within_scope():
    _app()
    prog = {3: {"color_b": 255, "dimmer": 100}}
    dlg = ChannelSelectDialog(prog, scope_fids=[3])
    dlg._checks["Intensity"].setChecked(False)  # Dimmer abwaehlen
    out = dlg.filter_programmer(prog)
    assert out == {3: {"color_b": 255}}


def test_active_scope_fids_follows_selection():
    from src.core.app_state import get_state
    st = get_state()
    st.set_selected_fids([5, 7, 9])
    assert st.active_scope_fids() == [5, 7, 9]
    st.set_selected_fids([])
    assert st.active_scope_fids() == []
