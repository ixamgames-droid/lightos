"""MIDI-2: Die MIDI-Ansicht bietet fuer GO/BACK kein Toggle/Flash mehr an.

Vorlagen und "Neues Mapping" legen GO als Druck-Aktion an; ein in die
Modus-Spalte getipptes "toggle" wird fuer GO/BACK auf "press" normalisiert.
"""
from PySide6.QtWidgets import QApplication

import src.core.midi.midi_mapper as mm
from src.ui.views import midi_view as midi_ui

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class _FakeMidi:
    available = False

    def list_inputs(self):
        return []

    def list_outputs(self):
        return []

    def subscribe(self, cb):
        pass

    def unsubscribe(self, cb):
        pass

    def subscribe_log(self, cb):
        pass

    def unsubscribe_log(self, cb):
        pass


class _FakeMtc:
    def list_ports(self):
        return []

    def subscribe(self, cb):
        pass

    def unsubscribe(self, cb):
        pass

    def fps(self):
        return 25.0


class _Mapper:
    def __init__(self):
        self.liste = []

    def get_mappings(self):
        return list(self.liste)

    def add_mapping(self, m):
        self.liste.append(m)

    def remove_mapping(self, i):
        self.liste.pop(i)


class _State:
    def __init__(self):
        self.midi_mapper = _Mapper()


def _view(monkeypatch):
    QApplication.instance() or QApplication([])
    st = _State()
    monkeypatch.setattr(midi_ui, "get_midi_manager", lambda: _FakeMidi())
    monkeypatch.setattr(midi_ui, "get_state", lambda: st)
    monkeypatch.setattr(midi_ui, "get_mtc_reader", lambda: _FakeMtc())
    return midi_ui.MidiView(), st.midi_mapper


def test_vorlage_und_neues_mapping_legen_go_als_druck_an(monkeypatch):
    view, mapper = _view(monkeypatch)
    try:
        view._template_notes_go()
        view._add_mapping()
        gos = [m for m in mapper.liste if m.action == mm.ACTION_EXECUTOR_GO]
        assert len(gos) == 11
        assert {m.button_mode for m in gos} == {mm.BUTTON_PRESS}
    finally:
        view.close()


def test_toggle_in_modus_spalte_wird_fuer_go_zu_druck(monkeypatch):
    view, mapper = _view(monkeypatch)
    try:
        view._add_mapping()
        view._map_table.item(0, 5).setText("toggle")
        assert mapper.liste[0].button_mode == mm.BUTTON_PRESS
        assert view._map_table.item(0, 5).text() == mm.BUTTON_PRESS
        # Zielwechsel auf Flash-Executor: toggle/flash bleiben dort waehlbar.
        view._map_table.item(0, 1).setText("executor_flash:1")
        view._map_table.item(0, 5).setText("flash")
        assert mapper.liste[0].button_mode == mm.BUTTON_FLASH
    finally:
        view.close()
