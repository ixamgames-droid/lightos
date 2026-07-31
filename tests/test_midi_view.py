"""QA-10: MidiView bleibt headless bedienbar und räumt Subscriber auf."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.core.midi.midi_manager import MidiMessage
from src.ui.views import midi_view as midi_ui


# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets WIRKLICH
# abbauen. `deleteLater()` allein stellt `DeferredDelete` nie zu — die Objekte
# ueberleben mitsamt Kindern, Signalen und (bei Views) Renderern. Segmentiert
# faellt das nicht auf, weil jede Datei allein laeuft; in einem Prozess mit
# genug angesammeltem Zustand ist es dieselbe Klasse Zeitzuender, die vor
# XPLAT-09 neun scheinbar gruene viz-Dateien zum Segfault brachte.
# Muster + Begruendung: tests/_qt_lifecycle.py, Vorbild test_views.py.
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    # QApplication lokal importieren: manche Dateien holen es nur INNERHALB
    # ihrer Tests, dann gibt es den Modulnamen hier nicht (3 Dateien liefen
    # genau darauf in einen NameError).
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


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


class _BrokenMidi(_FakeMidi):
    available = True

    def list_inputs(self):
        raise SystemError("ALSA unavailable")

    def list_outputs(self):
        raise RuntimeError("ALSA unavailable")


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
        view.deleteLater()
        _app().processEvents()

    assert not midi.message_callbacks
    assert not midi.log_callbacks
    assert not mtc.callbacks


def test_midi_view_survives_backend_scan_errors(monkeypatch):
    """Ein optionaler nativer MIDI-Backendfehler darf den UI-Start nicht
    abbrechen; die View zeigt stattdessen leere Portlisten."""
    _app()
    midi = _BrokenMidi()
    monkeypatch.setattr(midi_ui, "get_midi_manager", lambda: midi)
    monkeypatch.setattr(midi_ui, "get_state", lambda: _FakeState())
    monkeypatch.setattr(midi_ui, "get_mtc_reader", lambda: _FakeMtcReader())

    view = midi_ui.MidiView()
    try:
        assert view._combo_in.count() == 1
        assert "Keine MIDI" in view._combo_in.currentText()
        assert view._combo_out.count() == 1
        assert "Keine MIDI" in view._combo_out.currentText()
    finally:
        view.close()
        view.deleteLater()
        _app().processEvents()
