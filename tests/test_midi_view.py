"""QA-10: MidiView bleibt headless bedienbar und räumt Subscriber auf."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.core.midi.midi_manager import MidiMessage
from src.ui.views import midi_view as midi_ui


class _FakeMidi:
    available = False

    def __init__(self):
        self.message_callbacks = []
        self.log_callbacks = []

    def list_inputs(self):
        return []

    def list_outputs(self):
        return []

    def subscribe(self, callback):
        self.message_callbacks.append(callback)

    def unsubscribe(self, callback):
        self.message_callbacks.remove(callback)

    def subscribe_log(self, callback):
        self.log_callbacks.append(callback)

    def unsubscribe_log(self, callback):
        self.log_callbacks.remove(callback)


class _FakeMtcReader:
    def __init__(self):
        self.callbacks = []

    def list_ports(self):
        return []

    def subscribe(self, callback):
        self.callbacks.append(callback)

    def unsubscribe(self, callback):
        self.callbacks.remove(callback)

    def fps(self):
        return 25.0


class _FakeMapper:
    def get_mappings(self):
        return []


class _FakeState:
    midi_mapper = _FakeMapper()


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_midi_view_monitors_message_and_unsubscribes_on_close(monkeypatch):
    """Der echte UI-Pfad darf ohne MIDI-Hardware nicht leaken oder crashen."""
    _app()
    midi = _FakeMidi()
    mtc = _FakeMtcReader()
    monkeypatch.setattr(midi_ui, "get_midi_manager", lambda: midi)
    monkeypatch.setattr(midi_ui, "get_state", lambda: _FakeState())
    monkeypatch.setattr(midi_ui, "get_mtc_reader", lambda: mtc)

    view = midi_ui.MidiView()
    view.show()
    try:
        assert view._map_table.columnCount() == len(midi_ui.MAP_COLS)
        assert len(midi.message_callbacks) == len(midi.log_callbacks) == len(mtc.callbacks) == 1

        midi.message_callbacks[0](MidiMessage("Test-Port", 1, "cc", 7, 99))
        _app().processEvents()
        assert "CC" in view._console.toPlainText()

        QTest.mouseClick(view._chk_monitor, Qt.MouseButton.LeftButton)
        assert not view._monitor_active
    finally:
        view.close()

    assert not midi.message_callbacks
    assert not midi.log_callbacks
    assert not mtc.callbacks
