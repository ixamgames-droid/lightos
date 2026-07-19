"""XPLAT-03 — Art-Net-Input setzt SO_REUSEPORT (Linux-Port-Sharing).

Auf Linux teilt ``SO_REUSEADDR`` den UDP-Port NICHT (anders als Windows) → ohne
``SO_REUSEPORT`` wirft ``bind()`` "Address already in use", sobald eine 2. Art-Net-
App (QLC+ …) schon auf 6454 lauscht, und der Input bleibt still. Der sACN-Input
macht es bereits richtig; hier wird Art-Net angeglichen. Plattform-unabhängig über
einen Fake-Socket getestet (echte Constants gibt es auf Windows nicht).
"""
from __future__ import annotations
import socket as _socket
import time

import src.core.dmx.artnet_input as artnet_input

REUSEPORT = 15   # willkürlicher Wert; auf Windows fehlt socket.SO_REUSEPORT ganz


class _FakeSock:
    def __init__(self):
        self.opts = []
        self.bound = None
        self.timeout = None
        self.closed = False

    def setsockopt(self, level, opt, val):
        self.opts.append((level, opt, val))

    def bind(self, addr):
        self.bound = addr

    def settimeout(self, t):
        self.timeout = t

    def recvfrom(self, n):
        time.sleep(0.02)                 # kein tight-spin im RX-Thread
        raise _socket.timeout()

    def close(self):
        self.closed = True


def _patch_socket(monkeypatch, sock):
    monkeypatch.setattr(artnet_input.socket, "SO_REUSEPORT", REUSEPORT, raising=False)
    monkeypatch.setattr(artnet_input.socket, "socket", lambda *a, **k: sock)


def test_artnet_sets_reuseport_and_reuseaddr(monkeypatch):
    sock = _FakeSock()
    _patch_socket(monkeypatch, sock)
    inp = artnet_input.ArtNetReceiver()
    try:
        inp.start()
        assert (artnet_input.socket.SOL_SOCKET,
                artnet_input.socket.SO_REUSEADDR, 1) in sock.opts
        assert (artnet_input.socket.SOL_SOCKET, REUSEPORT, 1) in sock.opts   # neu
        assert sock.bound == ("0.0.0.0", artnet_input.ARTNET_PORT)
    finally:
        inp.stop()
    assert sock.closed


def test_artnet_binds_even_if_reuseport_unsupported(monkeypatch):
    # setsockopt(SO_REUSEPORT) wirft (wie auf Windows / altem Kernel) -> der guarded
    # Block schluckt es und bind() läuft trotzdem (Input bleibt funktionsfähig).
    class _Reject(_FakeSock):
        def setsockopt(self, level, opt, val):
            if opt == REUSEPORT:
                raise OSError("SO_REUSEPORT not supported")
            super().setsockopt(level, opt, val)

    sock = _Reject()
    _patch_socket(monkeypatch, sock)
    inp = artnet_input.ArtNetReceiver()
    try:
        inp.start()
        assert sock.bound == ("0.0.0.0", artnet_input.ARTNET_PORT)   # trotzdem gebunden
        assert inp.is_running()
    finally:
        inp.stop()


def test_reuseport_applied_before_bind(monkeypatch):
    # Reihenfolge: die Socket-Optionen müssen VOR bind() gesetzt sein.
    events = []
    sock = _FakeSock()

    real_setsockopt = sock.setsockopt
    real_bind = sock.bind
    sock.setsockopt = lambda l, o, v: (events.append(("opt", o)), real_setsockopt(l, o, v))[1]
    sock.bind = lambda a: (events.append(("bind", a)), real_bind(a))[1]
    _patch_socket(monkeypatch, sock)

    inp = artnet_input.ArtNetReceiver()
    try:
        inp.start()
        opt_idxs = [i for i, e in enumerate(events) if e[0] == "opt"]
        bind_idx = next(i for i, e in enumerate(events) if e[0] == "bind")
        assert opt_idxs and max(opt_idxs) < bind_idx     # alle Optionen vor bind
    finally:
        inp.stop()
