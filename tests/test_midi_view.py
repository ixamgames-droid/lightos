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


def test_midi_view_msc_einstellung_und_monitor(monkeypatch, tmp_path):
    """MIDI-5/NET-14: MSC-Box setzt die Einstellung, ruft den Mapper und
    zeigt MSC-Befehle im Monitor."""
    from src.core.midi import msc
    from src.core.midi.midi_manager import _decode
    _app()
    midi = _FakeMidi()
    applied = []

    class _MscMapper(_FakeMapper):
        def apply_msc_udp(self):
            applied.append(True)
            return True

    class _St:
        midi_mapper = _MscMapper()

    monkeypatch.setattr(midi_ui, "get_midi_manager", lambda: midi)
    monkeypatch.setattr(midi_ui, "get_state", lambda: _St())
    monkeypatch.setattr(midi_ui, "get_mtc_reader", lambda: _FakeMtcReader())
    import src.core.paths as paths
    monkeypatch.setattr(paths, "app_data_dir", lambda: str(tmp_path))
    st = msc.get_settings()
    alt = (st.enabled, st.device_id, st.udp_enabled, st.udp_host, st.udp_port)
    view = midi_ui.MidiView()
    try:
        view._spin_msc_dev.setValue(5)
        view._chk_msc_udp.setChecked(True)
        i = view._cmb_msc_host.findData("127.0.0.1")
        view._cmb_msc_host.setCurrentIndex(i)
        view._apply_msc()
        assert st.device_id == 5 and st.udp_enabled and applied
        # dauerhaft gespeichert (ui_prefs.json im isolierten Datenordner)
        import json
        gespeichert = json.loads((tmp_path / "ui_prefs.json").read_text())
        assert gespeichert["midi_msc"]["device_id"] == 5
        m = _decode([0xF0, 0x7F, 0x05, 0x02, 0x01, 0x01, ord("3"), 0xF7], "Pult")
        midi.message_callbacks[0](m)
        _app().processEvents()
        assert "MSC" in view._console.toPlainText()
    finally:
        st.enabled, st.device_id, st.udp_enabled, st.udp_host, st.udp_port = alt
        view.close()
        view.deleteLater()
        _app().processEvents()


def test_midi_view_msc_schnittstellenwahl(monkeypatch, tmp_path):
    """NET-14 Review: UDP-Empfang auf waehlbarer Netzwerkschnittstelle
    (Liste wie bei Art-Net/sACN) inkl. 'alle (0.0.0.0)' mit Hinweis."""
    from src.core.midi import msc
    import src.core.dmx.output_iface as oi
    import src.core.paths as paths
    _app()
    monkeypatch.setattr(paths, "app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(oi, "list_output_interfaces", lambda: [
        {"name": "lan0", "ip": "10.1.2.3", "netmask": "255.0.0.0",
         "broadcast": "10.255.255.255"}])

    class _MscMapper(_FakeMapper):
        def apply_msc_udp(self):
            return True

    class _St:
        midi_mapper = _MscMapper()

    monkeypatch.setattr(midi_ui, "get_midi_manager", lambda: _FakeMidi())
    monkeypatch.setattr(midi_ui, "get_state", lambda: _St())
    monkeypatch.setattr(midi_ui, "get_mtc_reader", lambda: _FakeMtcReader())
    st = msc.get_settings()
    alt = (st.enabled, st.device_id, st.udp_enabled, st.udp_host, st.udp_port)
    view = midi_ui.MidiView()
    try:
        cmb = view._cmb_msc_host
        daten = [cmb.itemData(i) for i in range(cmb.count())]
        assert "127.0.0.1" in daten and "10.1.2.3" in daten and "0.0.0.0" in daten
        assert not view._chk_msc_udp.isChecked()     # Standard bleibt aus
        cmb.setCurrentIndex(cmb.findData("0.0.0.0"))
        assert "alle" in view._lbl_msc_hint.text().lower()
        cmb.setCurrentIndex(cmb.findData("10.1.2.3"))
        view._apply_msc()
        assert st.udp_host == "10.1.2.3"
    finally:
        st.enabled, st.device_id, st.udp_enabled, st.udp_host, st.udp_port = alt
        view.close()
        view.deleteLater()
        _app().processEvents()
