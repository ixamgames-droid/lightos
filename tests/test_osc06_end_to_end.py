"""OSC-06 End-to-End: echtes UDP-OSC (python-osc) ueber 127.0.0.1 auf freien
Ports — freie Zuordnung, feste Adressen daneben, Uebergabe in den GUI-Thread,
Learn mit Absender und Rueckmeldung an einen Empfaenger."""
from __future__ import annotations

import socket
import threading
import time

import pytest

pytest.importorskip("pythonosc")
from pythonosc import dispatcher as osc_dispatcher  # noqa: E402
from pythonosc import osc_server as osc_srv  # noqa: E402
from pythonosc.udp_client import SimpleUDPClient  # noqa: E402

from src.core.osc import osc_zuordnung as oz  # noqa: E402
from src.core.osc.osc_server import OscSender, OscServer  # noqa: E402
from src.core.osc.osc_zuordnung import (  # noqa: E402
    BEREICH_100, Konfig, OscRueckmeldung, OscZuordnung, RueckmeldeKonfig,
    Zuordnung,
)


def _freier_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Ex:
    def __init__(self):
        self.fader_value = 1.0
        self.fader_function = "volume"
        self.stack = None
        self.gedrueckt: list = []
        self.threads: set = set()

    def press_btn(self, b):
        self.gedrueckt.append(b)
        self.threads.add(threading.get_ident())


class _PE:
    def __init__(self):
        self.executors = [_Ex() for _ in range(20)]

    def get_executor(self, slot):
        return self.executors[slot - 1]


class _OM:
    grand_master = 1.0
    blackout = False

    def set_grand_master(self, v):
        self.grand_master = v

    def set_blackout(self, v):
        self.blackout = bool(v)


class _State:
    def __init__(self):
        self.playback_engine = _PE()
        self.output_manager = _OM()


def _warte(bedingung, s=2.0, app=None):
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        if app is not None:
            app.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


@pytest.fixture
def server(monkeypatch):
    state = _State()
    import src.core.app_state as app_state
    monkeypatch.setattr(app_state, "get_state", lambda: state)
    import src.core.cueliste_ziel as cueliste_ziel
    globale: list = []
    monkeypatch.setattr(cueliste_ziel, "bediene_cueliste",
                        lambda st, aktion: globale.append(aktion))
    zu = OscZuordnung()
    port = _freier_port()
    srv = OscServer("127.0.0.1", port)
    srv._get_state = lambda: state
    srv._zuordnung = zu
    srv.start()
    client = SimpleUDPClient("127.0.0.1", port)
    yield srv, zu, state, client, globale
    srv.stop()


def test_freie_adresse_und_feste_adressen_nebeneinander(server):
    srv, zu, state, client, globale = server
    zu.konfigurieren(Konfig(zuordnungen=[
        Zuordnung("/Page1/Fader{n}", oz.ZIEL_FADER, versatz=-200, bereich=BEREICH_100),
        Zuordnung("/exec/{n}/go", oz.ZIEL_GO),
    ]))
    client.send_message("/Page1/Fader202", 25)
    client.send_message("/exec/5/go", 1.0)
    client.send_message("/exec/5/go", 0.0)
    # feste Adressen unveraendert
    client.send_message("/lightos/exec/3/fader", 0.6)
    client.send_message("/lightos/go", 1.0)
    pe = state.playback_engine
    assert _warte(lambda: pe.get_executor(2).fader_value == pytest.approx(0.25)
                  and pe.get_executor(5).gedrueckt == ["go"]
                  and pe.get_executor(3).fader_value == pytest.approx(0.6)
                  and globale == ["go"])
    time.sleep(0.15)
    assert pe.get_executor(5).gedrueckt == ["go"]     # Loslassen loeste nicht aus


def test_kaputte_pakete_stoeren_nicht(server):
    srv, zu, state, client, globale = server
    zu.konfigurieren(Konfig(zuordnungen=[Zuordnung("/f/{n}", oz.ZIEL_FADER)]))
    roh = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for paket in (b"", b"\x00", b"/f/1\x00\x00\x00,f\x00\x00", b"#bundle\x00kaputt",
                      b"\xff" * 64):
            roh.sendto(paket, srv._server.server_address)
    finally:
        roh.close()
    client.send_message("/f/1", "kein-wert")
    client.send_message("/f/1", 0.7)
    ex = state.playback_engine.get_executor(1)
    assert _warte(lambda: ex.fader_value == pytest.approx(0.7))
    assert srv._thread.is_alive()


def test_learn_ueber_udp_mit_absender(server):
    srv, zu, state, client, globale = server
    gelernt = threading.Event()
    box = []
    zu.lerne(lambda a, args, von: (box.append((a, args, von)), gelernt.set()))
    client.send_message("/Page1/Fader201", 42.0)
    assert gelernt.wait(2.0)
    adresse, args, von = box[0]
    assert adresse == "/Page1/Fader201" and args == (42.0,) and von == "127.0.0.1"
    assert oz.vorschlag_muster(adresse) == ("/Page1/Fader{n}", 201)


def test_uebergabe_in_den_gui_thread(server):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    srv, zu, state, client, globale = server
    zu.konfigurieren(Konfig(zuordnungen=[Zuordnung("/g", oz.ZIEL_GO, nummer=1)]))
    from PySide6.QtCore import QObject, Qt, Signal

    class _W(QObject):
        sig = Signal()

    w = _W()
    w.sig.connect(lambda: zu.abarbeiten(state), Qt.ConnectionType.QueuedConnection)
    zu.set_wecker(w.sig.emit)
    client.send_message("/g", 1.0)
    ex = state.playback_engine.get_executor(1)
    assert _warte(lambda: ex.gedrueckt == ["go"], app=app)
    assert ex.threads == {threading.get_ident()}      # angewandt im GUI-Thread


def test_qt_bruecke_der_app(monkeypatch):
    """installiere_qt_bruecke: Wecker gesetzt, Rueckmelde-Timer folgt aktiv."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    state = _State()
    import src.core.app_state as app_state
    monkeypatch.setattr(app_state, "get_state", lambda: state)
    br = oz.installiere_qt_bruecke()
    assert oz.get_osc_zuordnung()._wecker == br.wecken
    oz.anwenden(Konfig(zuordnungen=[Zuordnung("/q", oz.ZIEL_GO, nummer=2)]))
    try:
        threading.Thread(target=oz.get_osc_zuordnung().empfange,
                         args=("/q", (1,))).start()
        ex = state.playback_engine.get_executor(2)
        assert _warte(lambda: ex.gedrueckt == ["go"], app=app)
        assert not br._timer.isActive()
        oz.anwenden(Konfig(rueckmeldung=RueckmeldeKonfig(
            aktiv=True, ziel_ip="127.0.0.1", ziel_port=_freier_port())))
        assert br._timer.isActive()
    finally:
        oz.anwenden(Konfig())
    assert not br._timer.isActive()


def test_rueckmeldung_kommt_beim_empfaenger_an():
    port = _freier_port()
    empfangen: list = []
    d = osc_dispatcher.Dispatcher()
    d.set_default_handler(lambda a, *args: empfangen.append((a, args)))
    srv = osc_srv.ThreadingOSCUDPServer(("127.0.0.1", port), d)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        rm = OscRueckmeldung()
        rm.konfigurieren(RueckmeldeKonfig(aktiv=True, ziel_ip="127.0.0.1",
                                          ziel_port=port, executoren="1"))
        state = _State()
        state.playback_engine.get_executor(1).fader_value = 0.5
        assert rm.tick(state, jetzt=1.0) == 5
        assert _warte(lambda: len(empfangen) >= 5)
        d_ = {a: args[0] for a, args in empfangen}
        assert d_["/lightos/exec/1/fader"] == pytest.approx(0.5)
        assert d_["/lightos/exec/1/aktiv"] == 0
        assert d_["/lightos/blackout"] == 0
        assert rm.tick(state, jetzt=2.0) == 0
        state.output_manager.blackout = True
        assert rm.tick(state, jetzt=3.0) == 1
        assert _warte(lambda: ("/lightos/blackout", (1,)) in empfangen)
        rm.konfigurieren(RueckmeldeKonfig())      # schliesst den Sender
    finally:
        srv.shutdown()
        srv.server_close()


def test_osc_sender_meldet_erfolg_und_schliesst():
    s = OscSender("127.0.0.1", _freier_port())
    assert s.ziel[0] == "127.0.0.1"
    assert s.send("/x", 1) is True
    s.close()
    assert s.send("/x", 1) is False
    s.close()                                     # zweimal schadet nicht


def test_server_neustart_auf_demselben_port():
    port = _freier_port()
    srv = OscServer("127.0.0.1", port)
    srv.start()
    assert srv.is_running()
    srv.stop()
    assert not srv.is_running()
    srv.start()                                   # frueher: Address already in use
    srv.stop()
