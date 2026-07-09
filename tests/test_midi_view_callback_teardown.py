"""Regression fuer STAB-21: Worker-Singletons duerfen MidiView nicht pinnen."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication


class _FakeMidi:
    available = False

    def __init__(self):
        self.callbacks = []
        self.log_callbacks = []

    def subscribe(self, cb):
        self.callbacks.append(cb)

    def unsubscribe(self, cb):
        self.callbacks.remove(cb)

    def subscribe_log(self, cb):
        self.log_callbacks.append(cb)

    def unsubscribe_log(self, cb):
        self.log_callbacks.remove(cb)

    def list_inputs(self):
        return []

    def list_outputs(self):
        return []


class _FakeMtcReader:
    def __init__(self):
        self.callbacks = []

    def subscribe(self, cb):
        self.callbacks.append(cb)

    def unsubscribe(self, cb):
        self.callbacks.remove(cb)

    def list_ports(self):
        return []

    def fps(self):
        return 25.0


def test_midi_view_unregisters_midi_log_and_mtc_callbacks(monkeypatch):
    from src.ui.views import midi_view as module

    app = QApplication.instance() or QApplication([])
    midi = _FakeMidi()
    mtc = _FakeMtcReader()
    monkeypatch.setattr(module, "get_midi_manager", lambda: midi)
    monkeypatch.setattr(module, "get_mtc_reader", lambda: mtc)

    view = module.MidiView()

    assert len(midi.callbacks) == 1
    assert len(midi.log_callbacks) == 1
    assert len(mtc.callbacks) == 1

    view._teardown_callbacks()
    view._teardown_callbacks()  # closeEvent und destroyed duerfen sich nicht stoeren
    assert midi.callbacks == []
    assert midi.log_callbacks == []
    assert mtc.callbacks == []

    view.deleteLater()
    app.processEvents()
