"""OSC-05: GO/BACK/Exec-Tasten werten den OSC-Wert aus.

Ein TouchOSC-/Lemur-Taster sendet 1.0 beim Druecken und 0.0 beim Loslassen.
``_handle_go``/``_handle_back``/``_handle_exec`` ignorierten den Wert, also
loeste jeder Tastendruck ZWEIMAL aus (Cueliste sprang zwei Cues weiter).

Jetzt loest nur ein Wert >= halbe Skala aus (0..1, 0..100, 0..127/0..255);
ohne Argument wie bisher immer. Der Exec-Fader bleibt unveraendert.
Die Tests schicken echtes UDP-OSC an einen laufenden ``OscServer``.
"""
from __future__ import annotations

import socket
import time

import pytest

pytest.importorskip("pythonosc")
from pythonosc.udp_client import SimpleUDPClient  # noqa: E402

import src.core.cueliste_ziel as cueliste_ziel  # noqa: E402
from src.core.osc.osc_server import OscServer  # noqa: E402


class _Ex:
    def __init__(self):
        self.gedrueckt: list = []
        self.fader_value = 0.0

    def press_btn(self, b):
        self.gedrueckt.append(b)


class _PE:
    def __init__(self):
        self.executors = [_Ex(), _Ex()]


class _State:
    def __init__(self):
        self.playback_engine = _PE()


def _freier_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def osc(monkeypatch):
    state = _State()
    global_aufrufe: list = []
    monkeypatch.setattr(cueliste_ziel, "bediene_cueliste",
                        lambda st, aktion: global_aufrufe.append(aktion))
    port = _freier_port()
    srv = OscServer("127.0.0.1", port)
    srv._get_state = lambda: state
    srv.start()
    client = SimpleUDPClient("127.0.0.1", port)
    yield client, state, global_aufrufe
    srv.stop()


def _senden(client, nachrichten):
    for adresse, *wert in nachrichten:
        if wert:
            client.send_message(adresse, wert[0])
        else:
            client.send_message(adresse, [])
        time.sleep(0.01)
    time.sleep(0.25)


def test_touchosc_taster_go_loest_einmal_aus(osc):
    client, state, global_aufrufe = osc
    _senden(client, [("/lightos/go", 1.0), ("/lightos/go", 0.0),
                     ("/lightos/back", 1.0), ("/lightos/back", 0.0)])
    assert global_aufrufe == ["go", "back"]


def test_exec_taster_loest_einmal_aus(osc):
    client, state, _ = osc
    ex = state.playback_engine.executors[0]
    _senden(client, [("/lightos/exec/1/go", 1.0), ("/lightos/exec/1/go", 0.0),
                     ("/lightos/exec/1/back", 1.0), ("/lightos/exec/1/back", 0.0),
                     ("/lightos/exec/1/stop", 1), ("/lightos/exec/1/stop", 0)])
    assert ex.gedrueckt == ["go", "back", "stop"]


def test_ohne_argument_loest_wie_bisher_aus(osc):
    client, state, global_aufrufe = osc
    _senden(client, [("/lightos/go",), ("/lightos/exec/2/go",)])
    assert global_aufrufe == ["go"]
    assert state.playback_engine.executors[1].gedrueckt == ["go"]


@pytest.mark.parametrize("druck,los", [(100, 0), (255, 0), (127, 0), (1, 0),
                                       (True, False), ("1", "0")])
def test_skalen_werden_erkannt(osc, druck, los):
    client, state, global_aufrufe = osc
    _senden(client, [("/lightos/go", druck), ("/lightos/go", los)])
    assert global_aufrufe == ["go"]


@pytest.mark.parametrize("wert", [0.4, 30, 49])
def test_unter_halber_skala_kein_ausloesen(osc, wert):
    client, _state, global_aufrufe = osc
    _senden(client, [("/lightos/go", wert)])
    assert global_aufrufe == []


def test_exec_fader_unveraendert(osc):
    client, state, _ = osc
    ex = state.playback_engine.executors[0]
    _senden(client, [("/lightos/exec/1/fader", 0.25)])
    assert ex.fader_value == pytest.approx(0.25)
    _senden(client, [("/lightos/exec/1/fader", 0.0)])
    assert ex.fader_value == 0.0
    assert ex.gedrueckt == []


def test_pressed_hilfsfunktion():
    p = OscServer._is_pressed
    assert p(()) is True
    assert p((1.0,)) and p((0.5,)) and p((50,)) and p((64,)) and p((255,))
    assert not p((0.0,)) and not p((0.49,)) and not p((0,)) and not p((49,))
    assert not p(("off",)) and p(("on",))
