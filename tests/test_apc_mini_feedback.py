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
