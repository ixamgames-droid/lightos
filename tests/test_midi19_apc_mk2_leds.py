"""MIDI-19: APC mini mk2 — LED-Rueckmeldung beim Start, ein Umschalten pro
Druck, Seitentaste der aktiven Seite leuchtet.

Befund der Geraeteprobe (22.11.2026, Linux, echtes APC mini mk2):

1. Beim Start wurden nur die EINGAENGE automatisch verbunden; den Ausgang
   oeffnete allein der Knopf „APC LEDs" → „MIDI Ausgang: -", LEDs dunkel.
2. Ein Druck auf „APC LEDs" gab gestartet → geschlossen → gestartet.
3. Die Scene-Taste der aktiven Seite blieb dunkel: der mk2-Treiber sendete
   nur an die 64 Pads, die Seitentasten (Note 0x70..0x77, Akai-Protokoll)
   kannte er nicht. Das „kurz hell, dann dunkel" war das ``clear_all`` beim
   Start — bei leerer Konsole gab es danach nichts mehr, was leuchtet.

Kein echtes Geraet: ein Schein-MidiManager zeichnet auf, was an welchen Port
geht (Muster aus test_midi_led_portadressiert.py).
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

_app = QApplication.instance() or QApplication([])

from _qt_lifecycle import destroy_widget                              # noqa: E402

PORT = "APC mini mk2:APC mini mk2 Control 20:0"
NOTES = "APC mini mk2:APC mini mk2 Notes 20:1"


def _warten_bis(bedingung, ms=1000):
    ende = time.monotonic() + ms / 1000.0
    while not bedingung() and time.monotonic() < ende:
        QApplication.processEvents()
        time.sleep(0.002)
    return bedingung()


class _FakeManager:
    def __init__(self, ports):
        self.ports = list(ports)
        self._current = ""
        self.an_port: list[tuple[str, tuple]] = []
        self.open_calls: list[str] = []

    def list_outputs(self):
        return list(self.ports)

    def current_output_name(self):
        return self._current

    def open_output(self, name, **_kw):
        self.open_calls.append(name)
        self._current = name
        return True

    def send_message_to(self, port, msg):
        self.an_port.append((str(port), tuple(msg)))
        return True

    def close_aux_output(self, port):
        pass

    def open_all_inputs(self):
        pass

    def subscribe(self, *_a, **_k):
        pass

    def unsubscribe(self, *_a, **_k):
        pass


class _PE:
    def __init__(self, page=0):
        self.current_page = page
        self.executors = []

    def subscribe_page(self, cb):
        pass

    def unsubscribe_page(self, cb):
        pass


class _State:
    def __init__(self, page=0):
        self.playback_engine = _PE(page)
        self.programmer = {}

    def get_patched_fixtures(self):
        return []


@pytest.fixture
def mgr(monkeypatch):
    from src.core.midi import apc_mk2_feedback as fbm
    m = _FakeManager([PORT, NOTES, "Midi Through:Midi Through Port-0 14:0"])
    monkeypatch.setattr(fbm, "_RTMIDI", True)
    monkeypatch.setattr("src.core.midi.midi_manager.get_midi_manager", lambda: m)
    return m


@pytest.fixture
def state(monkeypatch):
    st = _State(page=0)
    monkeypatch.setattr("src.core.app_state.get_state", lambda: st)
    return st


def _knopf_noten(m, note):
    """Velocities, die an die Scene-/Track-Taste ``note`` gingen (Kanal 1)."""
    return [msg[2] for port, msg in m.an_port
            if port == PORT and msg[0] == 0x90 and msg[1] == note]


class _Canvas:
    def __init__(self, widgets=()):
        self._w = list(widgets)
        self.active_bank = 0

    def findChildren(self, cls):
        return [w for w in self._w if isinstance(w, cls)]


# ── (3) Seitentasten nach Akai-Protokoll ──────────────────────────────────────

def test_seitentasten_noten_nach_akai_protokoll():
    from src.core.midi import apc_mk2_feedback as fbm
    assert fbm.SCENE_BTNS == list(range(0x70, 0x78))
    assert fbm.TRACK_BTNS == list(range(0x64, 0x6C))
    # dieselben Noten wie Vorlage und Bibliothek
    from src.ui.virtualconsole.controller_templates import CONTROLLERS
    assert CONTROLLERS["apc_mini_mk2"]["scene"] == fbm.SCENE_BTNS
    assert CONTROLLERS["apc_mini_mk2"]["track"] == fbm.TRACK_BTNS


def test_aktive_seite_leuchtet_und_folgt_dem_wechsel(mgr, state):
    from src.core.midi import apc_mk2_feedback as fbm
    fb = fbm.ApcMk2Feedback(_Canvas(), port_hint="APC mini mk2")
    assert fb.is_connected
    try:
        fb._update()
        assert _knopf_noten(mgr, 0x70)[-1] == fbm.LED_AN, "Seite 1 muss leuchten"
        for n in range(0x71, 0x78):
            assert _knopf_noten(mgr, n)[-1] == fbm.LED_AUS
        state.playback_engine.current_page = 3
        fb._update()
        assert _knopf_noten(mgr, 0x70)[-1] == fbm.LED_AUS
        assert _knopf_noten(mgr, 0x73)[-1] == fbm.LED_AN, "LED folgt dem Seitenwechsel"
        # Diff-Update: unveraendert -> nichts Neues gesendet
        vorher = len(mgr.an_port)
        fb._update()
        assert len(mgr.an_port) == vorher
    finally:
        fb.close()
    assert _knopf_noten(mgr, 0x73)[-1] == fbm.LED_AUS, "beim Schliessen aus"


def test_aktive_vc_taste_laesst_pad_leuchten(mgr, state, monkeypatch):
    from src.core.midi import apc_mk2_feedback as fbm
    from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
    b = VCButton("FX")
    b.midi_type = "note_on"
    b.midi_data1 = 20
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.pad_style = "solid"
    fb = fbm.ApcMk2Feedback(_Canvas([b]), port_hint="APC mini mk2")
    fb.ripple_enabled = False
    try:
        fb._update()
        pad = [msg for port, msg in mgr.an_port if port == PORT and msg[1] == 20]
        assert pad[-1][0] == fbm.DIM, "belegt, inaktiv = gedimmt"
        monkeypatch.setattr(fb, "_is_active", lambda w: True)
        fb._update()
        pad = [msg for port, msg in mgr.an_port if port == PORT and msg[1] == 20]
        assert pad[-1][0] == fbm.FULL and pad[-1][2] != fbm.OFF, "aktiv = hell"
    finally:
        fb.close()
        destroy_widget(b, _app)


# ── (1) Start mit erkanntem mk2 ───────────────────────────────────────────────

@pytest.fixture
def ansicht(mgr, state, monkeypatch):
    from src.ui.views import virtual_console_view as vcv
    monkeypatch.setattr(vcv, "_apc_auto_erlaubt", lambda: True)
    v = vcv.VirtualConsoleView()
    yield v
    fb = getattr(v, "_apc_feedback", None)
    if fb is not None:
        fb.close()
        v._apc_feedback = None
    destroy_widget(v, _app)


def test_start_mit_erkanntem_mk2_startet_feedback(ansicht, mgr):
    from src.core.midi.apc_mk2_feedback import ApcMk2Feedback
    v = ansicht
    assert v._apc_feedback is None
    v.apc_leds_automatisch()
    assert isinstance(v._apc_feedback, ApcMk2Feedback)
    assert v._btn_apc_leds.isChecked()
    assert mgr.open_calls == [PORT], "Control-Port, nicht Notes/Midi Through"
    assert _knopf_noten(mgr, 0x70)[-1] == 1, "aktive Seite leuchtet sofort"
    # zweiter Auto-Connect-Lauf: kein zweites Oeffnen
    v.apc_leds_automatisch()
    assert mgr.open_calls == [PORT]


def test_hauptfenster_auto_connect_ruft_den_led_start(mgr, monkeypatch):
    from src.ui.main_window import MainWindow
    monkeypatch.delenv("LIGHTOS_NO_MIDI_AUTOCONNECT", raising=False)
    monkeypatch.setattr("src.core.timecode.mtc_cues.verdrahten", lambda mm: None)
    aufrufe = []

    class _VC:
        def apc_leds_automatisch(self):
            aufrufe.append(1)

    class _Fenster:
        _vc_view = _VC()

    MainWindow._auto_connect_midi(_Fenster())
    assert aufrufe == [1]


def test_kein_auto_start_nach_bewusstem_ausschalten_und_neustart_nach_einstecken(
        ansicht, mgr):
    v = ansicht
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(1)
    try:
        v.apc_leds_automatisch()
        assert v._apc_feedback is not None
        # Geraet abgezogen -> Feedback endet, Knopf aus
        mgr.ports = []
        v.apc_leds_automatisch()
        assert v._apc_feedback is None and not v._btn_apc_leds.isChecked()
        # wieder eingesteckt -> startet von selbst
        mgr.ports = [PORT, NOTES]
        v.apc_leds_automatisch()
        assert v._apc_feedback is not None
        # Robin schaltet bewusst aus -> bleibt aus
        t0 = time.monotonic()
        _warten_bis(lambda: time.monotonic() - t0 > 0.01, 1000)
        QTest.mouseClick(v._btn_apc_leds, Qt.MouseButton.LeftButton)
        assert v._apc_feedback is None
        v.apc_leds_automatisch()
        assert v._apc_feedback is None
    finally:
        hints.setMouseDoubleClickInterval(alt)


def test_ohne_echte_app_kein_auto_start(mgr, state):
    from src.ui.views import virtual_console_view as vcv
    v = vcv.VirtualConsoleView()
    try:
        v.apc_leds_automatisch()
        assert v._apc_feedback is None, "STAB-39: Tests/Probelaeufe senden nichts"
    finally:
        destroy_widget(v, _app)


def test_andere_mk2_geraete_sind_kein_apc_mini_mk2():
    from src.ui.views.virtual_console_view import _apc_mk2_port
    assert _apc_mk2_port(["APC Key 25 mk2", "APC40 mkII"]) is None
    assert _apc_mk2_port(["MIDIOUT2 (APC mini mk2)", "APC mini mk2"]) == \
        "MIDIOUT2 (APC mini mk2)"


# ── (2) ein Druck = genau ein Umschalten ──────────────────────────────────────

def _zaehlen(monkeypatch):
    from src.core.midi import apc_mk2_feedback as fbm
    log = []
    orig_attach, orig_close = fbm.ApcMk2Feedback.attach, fbm.ApcMk2Feedback.close

    def attach(self, *a, **k):
        log.append("an")
        return orig_attach(self, *a, **k)

    def close(self):
        log.append("aus")
        return orig_close(self)

    monkeypatch.setattr(fbm.ApcMk2Feedback, "attach", attach)
    monkeypatch.setattr(fbm.ApcMk2Feedback, "close", close)
    return log


def test_doppeltippen_schaltet_nur_einmal(ansicht, monkeypatch):
    """Zweites Umschalten im Doppelklick-Fenster (Doppeltippen/Prellen) war
    der Hergang an → aus → an aus dem Log."""
    log = _zaehlen(monkeypatch)
    v = ansicht
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(5000)
    try:
        k = v._btn_apc_leds
        QTest.mouseClick(k, Qt.MouseButton.LeftButton)
        mitte = k.rect().center()
        QTest.mouseDClick(k, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, mitte)
        QTest.mouseRelease(k, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, mitte)
        QApplication.processEvents()
        assert log == ["an"], log
        assert k.isChecked() and v._apc_feedback is not None
    finally:
        hints.setMouseDoubleClickInterval(alt)


def test_zwei_getrennte_druecke_schalten_an_und_aus(ansicht, monkeypatch):
    log = _zaehlen(monkeypatch)
    v = ansicht
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(1)
    try:
        k = v._btn_apc_leds
        QTest.mouseClick(k, Qt.MouseButton.LeftButton)
        assert log == ["an"]
        t0 = time.monotonic()
        _warten_bis(lambda: time.monotonic() - t0 > 0.01, 1000)
        QTest.mouseClick(k, Qt.MouseButton.LeftButton)
        assert log == ["an", "aus"]
        assert not k.isChecked() and v._apc_feedback is None
    finally:
        hints.setMouseDoubleClickInterval(alt)


def test_fingertipp_schaltet_genau_einmal(ansicht, monkeypatch):
    log = _zaehlen(monkeypatch)
    v = ansicht
    v.resize(1400, 700)
    v.show()
    QApplication.processEvents()
    k = v._btn_apc_leds
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(1)
    try:
        dev = QTest.createTouchDevice()
        win = v.window()
        q = k.mapTo(win, k.rect().center())
        QTest.touchEvent(win, dev).press(0, q, win).commit()
        QTest.touchEvent(win, dev).release(0, q, win).commit()
        _warten_bis(lambda: bool(log), 1000)
        QApplication.processEvents()
        assert log == ["an"], log
        assert k.isChecked()
    finally:
        hints.setMouseDoubleClickInterval(alt)
