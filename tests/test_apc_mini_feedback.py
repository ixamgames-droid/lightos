"""Regressionstest fuer APC-Mini-LED-Feedback (Open Point AUDIT-exclude_note).

Sichert ab, dass der tote exclude_note/include_note/_excluded-Mechanismus
entfernt wurde und set_led im Update-Loop unbedingt feuert (konsistent zur
mk2-Variante, die ebenfalls keinen Exclude-Mechanismus hat).
"""
from src.core.midi.apc_mini_feedback import (
    APCMiniFeedback, LED_OFF, LED_GREEN, LED_GREEN_BLINK, LED_RED, LED_YELLOW,
)


class _FakeOut:
    def __init__(self):
        self.sent: list[tuple[int, int, int]] = []

    def send_message(self, msg):
        self.sent.append(tuple(msg))


class _FakeExec:
    def __init__(self, stack=None, output=False, flash=False):
        self.stack = stack
        self._flash_active = flash
        self._out = output

    def get_output(self):
        return self._out


class _FakePE:
    def __init__(self, execs, page=0):
        self.executors = execs
        self.current_page = page


class _FakeState:
    def __init__(self, pe):
        self.playback_engine = pe


def _make_fb():
    # port_hint, der keinen realen Port trifft -> _out bleibt None,
    # danach setzen wir einen Fake-Out fuer die Assertions.
    fb = APCMiniFeedback(port_hint="__no_such_port__")
    out = _FakeOut()
    fb._out = out
    return fb, out


class _FakeManager:
    """Minimaler MidiManager-Ersatz mit umschaltbarem Ausgang."""

    def __init__(self, ports, current=""):
        self._ports = list(ports)
        self._current = current
        self.sent: list[tuple[int, ...]] = []
        self.open_calls: list[str] = []

    def list_outputs(self):
        return list(self._ports)

    def current_output_name(self):
        return self._current

    def open_output(self, name, **_kw):
        self.open_calls.append(name)
        self._current = name
        return True

    def send_message(self, msg):
        self.sent.append(tuple(msg))
        return True


def test_led_feedback_does_not_hijack_a_foreign_output(monkeypatch):
    """Das Einschalten der LEDs darf einen fremden, bereits offenen Ausgang
    nicht wegreissen (der gehoert der MIDI-Ansicht bzw. dem Mapping-Feedback)."""
    from src.core.midi import apc_mini_feedback as mod

    mgr = _FakeManager(["APC mini mk2", "Anderes Pult"], current="Anderes Pult")
    monkeypatch.setattr(mod, "_RTMIDI", True)
    monkeypatch.setattr("src.core.midi.midi_manager.get_midi_manager", lambda: mgr)

    fb = APCMiniFeedback(port_hint="APC")
    assert fb.is_connected is False
    assert mgr.open_calls == [], "fremder Ausgang wurde uebernommen"
    assert mgr.current_output_name() == "Anderes Pult"


def test_led_feedback_stops_sending_when_output_switches_away(monkeypatch):
    """Schaltet jemand den geteilten Ausgang um, duerfen keine Pad-Noten mehr
    rausgehen — sonst klimpern sie auf dem fremden Geraet (Windows: GS Synth)."""
    from src.core.midi import apc_mini_feedback as mod

    mgr = _FakeManager(["APC mini mk2"], current="")
    monkeypatch.setattr(mod, "_RTMIDI", True)
    monkeypatch.setattr("src.core.midi.midi_manager.get_midi_manager", lambda: mgr)

    fb = APCMiniFeedback(port_hint="APC")
    assert fb.is_connected is True
    fb.set_led(3, LED_GREEN)
    assert len(mgr.sent) == 1

    mgr._current = "Anderes Pult"          # jemand schaltet um
    fb.set_led(4, LED_RED)
    assert len(mgr.sent) == 1, "LED-Note ging an ein fremdes Geraet"


def test_close_does_not_close_the_shared_manager_port(monkeypatch):
    """Der geteilte Manager-Port gehoert nicht uns — nicht schliessen."""
    from src.core.midi import apc_mini_feedback as mod

    mgr = _FakeManager(["APC mini mk2"], current="")
    mgr.closed = False
    mgr.close_port = lambda: setattr(mgr, "closed", True)
    monkeypatch.setattr(mod, "_RTMIDI", True)
    monkeypatch.setattr("src.core.midi.midi_manager.get_midi_manager", lambda: mgr)

    fb = APCMiniFeedback(port_hint="APC")
    assert fb.is_connected is True
    fb.close()
    assert mgr.closed is False, "geteilter Manager-Port wurde geschlossen"


def test_close_releases_an_own_winmm_handle():
    """WinMM-Fallback (ARM-Windows, kein python-rtmidi): der EIGENE midiOut-
    Handle muss beim Schliessen freigegeben werden, sonst bleibt das Geraet
    bis zum Prozessende belegt."""
    class _OwnOut:
        def __init__(self):
            self.closed = False
            self.sent = []

        def send_message(self, msg):
            self.sent.append(tuple(msg))

        def close_port(self):
            self.closed = True

    fb = APCMiniFeedback(port_hint="__no_such_port__")
    own = _OwnOut()
    fb._out = own
    fb._out_name = None            # eigener Handle, nicht der Manager
    fb.close()
    assert own.closed is True, "eigener WinMM-Handle wurde nicht geschlossen"


def test_exclude_mechanism_removed():
    """exclude_note/include_note/_excluded duerfen nicht mehr existieren."""
    assert not hasattr(APCMiniFeedback, "exclude_note")
    assert not hasattr(APCMiniFeedback, "include_note")
    fb, _ = _make_fb()
    try:
        assert not hasattr(fb, "_excluded")
    finally:
        fb.close()


def test_update_sets_leds_unconditionally():
    """_update feuert set_led fuer GO/Flash/Back/Seite ohne Exclude-Filter."""
    fb, out = _make_fb()
    try:
        # Exec 0: aktiver Stack mit Output -> GO gruen.
        # Exec 1: Stack ohne Output -> GO gruen-blink.
        # Exec 2: kein Stack -> GO aus; Flash gehalten -> Flash rot.
        execs = [
            _FakeExec(stack=object(), output=True),
            _FakeExec(stack=object(), output=False),
            _FakeExec(stack=None, output=False, flash=True),
        ]
        fb._state = _FakeState(_FakePE(execs, page=2))
        fb._update()

        sent = dict((note, vel) for _st, note, vel in out.sent)

        # GO-Reihe (GRID_ROW0)
        assert sent[fb.GRID_ROW0[0]] == LED_GREEN
        assert sent[fb.GRID_ROW0[1]] == LED_GREEN_BLINK
        assert sent[fb.GRID_ROW0[2]] == LED_OFF
        # Flash-Reihe (GRID_ROW1): Exec 2 haelt Flash -> rot
        assert sent[fb.GRID_ROW1[2]] == LED_RED
        # Seiten-Buttons: aktive Seite (2) gelb, andere aus
        assert sent[fb.SIDE_BTNS[2]] == LED_YELLOW
        assert sent[fb.SIDE_BTNS[0]] == LED_OFF
    finally:
        fb.close()
