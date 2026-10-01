"""UI-65: Linux-Reste.

(a) LNX-06: Strg+5 oeffnete 2026-07 unter X11 die Simple-Desk-Sektion nicht.
    Heute bindet das MainWindow Strg+1…N einheitlich per QAction. Der Test
    prueft JEDE Sektion — per Tastendruck auf das echte (offscreen) Fenster
    und ueber die QAction — und dass keine zweite Aktion dieselbe Strg+Zahl
    belegt (ein Doppel macht den Shortcut in Qt „ambiguous" und stumm).
(b) MidiManager.open_input baute ``rtmidi.MidiIn()`` ohne try — bei kaputtem
    ALSA-Backend warf schon der Klick auf „Eingang oeffnen". Jetzt: False +
    Meldung im MIDI-Log, Circuit-Breaker gesetzt/respektiert, die View zeigt
    nicht gruen.
"""
import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAction, QKeySequence  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core.midi import midi_manager as mm  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ── (a) Strg+Zahl → Sektion ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def main_window():
    _app()
    from src.ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    QTest.qWaitForWindowExposed(w)
    yield w
    w.close()
    w.deleteLater()
    _app().processEvents()


_DIGIT_KEYS = [getattr(Qt.Key, f"Key_{n}") for n in range(1, 10)]


def _section_count(w) -> int:
    n = len(w._section_btns)
    assert n == w._stack.count(), "Sektions-Buttons und Stack-Seiten weichen ab"
    assert 1 <= n <= 9, "Strg+Zahl reicht nur fuer 1..9 Sektionen"
    return n


def _go_elsewhere(w, idx):
    other = 0 if idx != 0 else 1
    w._switch_section(other)
    assert w._stack.currentIndex() == other


def test_strg_zahl_per_tastendruck_oeffnet_jede_sektion(main_window):
    w = main_window
    n = _section_count(w)
    for idx in range(n):
        _go_elsewhere(w, idx)
        w.activateWindow()
        w.setFocus()
        QTest.keyClick(w, _DIGIT_KEYS[idx], Qt.KeyboardModifier.ControlModifier)
        _app().processEvents()
        assert w._stack.currentIndex() == idx, (
            f"Strg+{idx + 1} oeffnete nicht Sektion "
            f"„{w._section_btns[idx].text()}“")
        assert w._section_btns[idx].isChecked()


def test_strg_5_oeffnet_simple_desk(main_window):
    """Der konkrete LNX-06-Befund: Strg+5 → Simple Desk."""
    w = main_window
    idx = next(i for i, b in enumerate(w._section_btns)
               if "Simple Desk" in (b.toolTip() or b.text()) or b.text() == "Simple Desk")
    assert idx == 4
    _go_elsewhere(w, idx)
    QTest.keyClick(w, Qt.Key.Key_5, Qt.KeyboardModifier.ControlModifier)
    _app().processEvents()
    assert w._stack.currentWidget().isAncestorOf(w._simple_desk)


def test_jede_strg_zahl_ist_genau_einmal_vergeben(main_window):
    """Keine konkurrierende Aktion/QShortcut mit derselben Strg+Zahl im
    Fenster — Qt loest bei Doppelbelegung gar nichts aus."""
    from PySide6.QtGui import QShortcut
    w = main_window
    n = _section_count(w)
    wanted = {QKeySequence(f"Ctrl+{i + 1}").toString(): i for i in range(n)}
    hits = {k: 0 for k in wanted}
    for act in w.findChildren(QAction):
        for seq in act.shortcuts():
            key = seq.toString()
            if key in hits:
                hits[key] += 1
    for sc in w.findChildren(QShortcut):
        key = sc.key().toString()
        if key in hits:
            hits[key] += 1
    assert all(c == 1 for c in hits.values()), hits


def test_qaction_trigger_oeffnet_jede_sektion(main_window):
    w = main_window
    n = _section_count(w)
    by_key = {}
    for act in w.actions():
        by_key[act.shortcut().toString()] = act
    for idx in range(n):
        _go_elsewhere(w, idx)
        act = by_key[QKeySequence(f"Ctrl+{idx + 1}").toString()]
        act.trigger()
        assert w._stack.currentIndex() == idx


# ── (b) MidiIn()-Konstruktor wirft ─────────────────────────────────────────

class _BoomMidiIn:
    calls = 0

    def __init__(self, *a, **k):
        type(self).calls += 1
        raise SystemError("MidiInAlsa::initialize: error creating ALSA sequencer client object.")


@pytest.fixture
def rtmidi_kaputt(monkeypatch):
    _BoomMidiIn.calls = 0
    stub = types.SimpleNamespace(MidiIn=_BoomMidiIn, MidiOut=_BoomMidiIn)
    monkeypatch.setattr(mm, "rtmidi", stub, raising=False)
    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm, "_USE_WINMM", False)
    return stub


def test_open_input_meldet_fehler_statt_zu_werfen(rtmidi_kaputt):
    mgr = mm.MidiManager()
    logs = []
    mgr.subscribe_log(logs.append)
    try:
        assert mgr.open_input("APC mini mk2") is False
        assert "APC mini mk2" not in mgr._inputs
        assert any("MIDI Input Fehler" in t for t in logs), logs
        # Breaker gesetzt: der Hotplug-Scan baut keinen weiteren Client.
        assert mgr._rtmidi_retry_after > 0
        calls = _BoomMidiIn.calls
        assert mgr.list_inputs() == []
        assert mgr.open_input("APC mini mk2") is False
        assert _BoomMidiIn.calls == calls, "Breaker ignoriert: neuer ALSA-Client"
        # Auto-Connect bleibt ebenfalls ruhig.
        assert mgr.open_all_inputs() == 0
    finally:
        mgr.close_all()


def test_open_port_fehler_setzt_keinen_backend_breaker(monkeypatch):
    class _BusyIn:
        closed = False

        def get_port_count(self):
            return 1

        def get_port_name(self, i):
            return "APC"

        def open_port(self, i):
            raise RuntimeError("Device or resource busy")

        def close_port(self):
            type(self).closed = True

    monkeypatch.setattr(mm, "rtmidi", types.SimpleNamespace(MidiIn=_BusyIn, MidiOut=_BusyIn),
                        raising=False)
    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm, "_USE_WINMM", False)
    mgr = mm.MidiManager()
    try:
        assert mgr.open_input("APC") is False
        assert mgr._rtmidi_retry_after == 0.0
        assert _BusyIn.closed
    finally:
        mgr.close_all()


def test_open_input_erfolg_liefert_true(monkeypatch):
    class _OkIn:
        def get_port_count(self):
            return 1

        def get_port_name(self, i):
            return "APC"

        def open_port(self, i):
            pass

        def set_callback(self, cb):
            pass

        def close_port(self):
            pass

    monkeypatch.setattr(mm, "rtmidi", types.SimpleNamespace(MidiIn=_OkIn, MidiOut=_OkIn),
                        raising=False)
    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm, "_USE_WINMM", False)
    mgr = mm.MidiManager()
    try:
        assert mgr.open_input("APC") is True
        assert mgr.open_input("APC") is True  # schon offen
        assert mgr.open_input("Fehlt") is False
    finally:
        mgr.close_all()


class _ViewMidi:
    available = True

    def __init__(self, result):
        self._result = result
        self.log_callbacks = []

    def list_inputs(self):
        return ["APC"]

    def list_outputs(self):
        return []

    def subscribe(self, cb):
        pass

    def unsubscribe(self, cb):
        pass

    def subscribe_log(self, cb):
        self.log_callbacks.append(cb)

    def unsubscribe_log(self, cb):
        if cb in self.log_callbacks:
            self.log_callbacks.remove(cb)

    def open_input(self, port):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _Mtc:
    def list_ports(self):
        return []

    def subscribe(self, cb):
        pass

    def unsubscribe(self, cb):
        pass

    def fps(self):
        return 25.0


class _State:
    class midi_mapper:  # noqa: N801
        @staticmethod
        def get_mappings():
            return []


def _view(monkeypatch, result):
    from src.ui.views import midi_view as midi_ui
    _app()
    midi = _ViewMidi(result)
    monkeypatch.setattr(midi_ui, "get_midi_manager", lambda: midi)
    monkeypatch.setattr(midi_ui, "get_state", lambda: _State())
    monkeypatch.setattr(midi_ui, "get_mtc_reader", lambda: _Mtc())
    view = midi_ui.MidiView()
    view._combo_in.setCurrentText("APC")
    return view


@pytest.mark.parametrize("result", [False, SystemError("ALSA kaputt")])
def test_view_zeigt_bei_fehler_nicht_gruen(monkeypatch, result):
    view = _view(monkeypatch, result)
    try:
        view._open_input()  # darf nicht werfen
        assert "#00cc66" not in view._lbl_midi_status.styleSheet()
        assert "#ff5555" in view._lbl_midi_status.styleSheet()
        if isinstance(result, Exception):
            assert "ALSA kaputt" in view._console.toPlainText()
    finally:
        view.close()
        view.deleteLater()
        _app().processEvents()


def test_view_zeigt_bei_erfolg_gruen(monkeypatch):
    view = _view(monkeypatch, True)
    try:
        view._open_input()
        assert "#00cc66" in view._lbl_midi_status.styleSheet()
        assert view._lbl_midi_status.text() == "IN: APC"
    finally:
        view.close()
        view.deleteLater()
        _app().processEvents()


def test_breaker_aktiv_evakuiert_offenen_eingang_nicht(monkeypatch):
    """Review UI-65: bei aktivem Breaker liefert der Scan [], ein laufender
    Handle saehe tot aus. open_input darf ihn dann nicht schliessen."""
    import time as _t
    geschlossen = []

    class _Offen:
        def close_port(self):
            geschlossen.append(True)

    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm, "_USE_WINMM", False)
    mgr = mm.MidiManager()
    try:
        mgr._inputs["APC"] = _Offen()
        mgr._rtmidi_retry_after = _t.monotonic() + 30
        assert mgr.open_input("APC") is True
        assert "APC" in mgr._inputs
        assert geschlossen == []
    finally:
        mgr._inputs.clear()
        mgr.close_all()


def test_unbekannter_port_steht_im_log(monkeypatch):
    """Review UI-65: die rote Statuszeile verweist aufs MIDI-Log — dann muss
    dort auch etwas stehen."""
    class _OkIn:
        def get_port_count(self):
            return 1

        def get_port_name(self, i):
            return "APC"

        def close_port(self):
            pass

    monkeypatch.setattr(mm, "rtmidi", types.SimpleNamespace(MidiIn=_OkIn, MidiOut=_OkIn),
                        raising=False)
    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm, "_USE_WINMM", False)
    mgr = mm.MidiManager()
    log = []
    mgr._log_callbacks.append(log.append)
    try:
        assert mgr.open_input("Fehlt") is False
        assert any("Fehlt" in z for z in log)
    finally:
        mgr.close_all()
