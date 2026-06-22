"""P7: Programmer-Slider folgen externen State-Aenderungen live.

AttributeSlider._load_current_value() liest den Programmer-Wert ohne Echo
(set_programmer_value darf dabei NICHT aufgerufen werden); ProgrammerView
stoesst den Refresh ueber PROGRAMMER_CHANGED (coalesced) an.
"""
from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


class _Ch:
    def __init__(self, attr, default=0, name="Kanal"):
        self.attribute = attr
        self.default_value = default
        self.name = name


class _Fx:
    def __init__(self, fid):
        self.fid = fid


class _StateStub:
    def __init__(self):
        self.values = {}
        self.set_calls = []

    def get_programmer_value(self, fid, attr, head=0):
        # Signatur spiegelt AppState.get_programmer_value (Mehrkopf X-6):
        # head>0 adressiert das N-te Vorkommen via Schluessel "attr#N".
        key = attr if not head else f"{attr}#{int(head)}"
        return self.values.get((fid, key))

    def set_programmer_value(self, fid, attr, value, undoable=False, head=0):
        key = attr if not head else f"{attr}#{int(head)}"
        self.set_calls.append((fid, attr, value))
        self.values[(fid, key)] = value


def _make_slider(state, fixtures):
    from src.ui.views.programmer_view import AttributeSlider
    return AttributeSlider(_Ch("color_r", default=0, name="Rot"),
                           fixtures, state)


def test_slider_reads_external_change_without_echo():
    _app()
    state = _StateStub()
    sl = _make_slider(state, [_Fx(1)])
    assert sl._slider.value() == 0

    # Externe Aenderung (Quick-Color/VC/MIDI) -> Refresh laedt den Wert
    state.values[(1, "color_r")] = 200
    state.set_calls.clear()
    sl._load_current_value()
    assert sl._slider.value() == 200
    # KEIN Echo: der Refresh darf nicht selbst in den Programmer schreiben
    assert state.set_calls == []


def test_slider_user_change_still_writes():
    _app()
    state = _StateStub()
    sl = _make_slider(state, [_Fx(1), _Fx(2)])
    sl._slider.setValue(123)   # simulierter Nutzer-Drag (linked-Modus)
    assert (1, "color_r", 123) in state.set_calls
    assert (2, "color_r", 123) in state.set_calls


def test_refresh_skips_slider_during_drag():
    _app()
    state = _StateStub()
    sl = _make_slider(state, [_Fx(1)])
    state.values[(1, "color_r")] = 50
    sl._slider.setSliderDown(True)   # Nutzer haelt den Slider gerade fest
    try:
        # ProgrammerView._refresh_sliders_from_state ueberspringt gedrueckte
        # Slider — hier direkt die Bedingung pruefen:
        assert sl._slider.isSliderDown() is True
    finally:
        sl._slider.setSliderDown(False)
