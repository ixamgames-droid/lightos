"""XPLAT-06 — wählbare Ausgangs-NIC für DMX-/Laser-Broadcast/Multicast.

Ohne ``LIGHTOS_OUTPUT_IFACE`` bleibt alles beim OS-Routing (Windows unverändert).
Ist die Env-Variable gesetzt, binden Art-Net/sACN/IDN ihre Sende-Sockets an die
gewählte NIC (Linux Multi-NIC-Rigs). Plattform-unabhängig über Fake-Sockets getestet.
"""
from __future__ import annotations
import socket as _socket

import pytest

from src.core.dmx import output_iface as oi

IFACE = "192.168.5.42"


class _FakeSock:
    def __init__(self):
        self.opts = []
        self.bound = None

    def bind(self, addr):
        self.bound = addr

    def setsockopt(self, level, opt, val):
        self.opts.append((level, opt, val))


# ── output_interface_ip ──────────────────────────────────────────────────────

def test_iface_ip_none_when_unset(monkeypatch):
    monkeypatch.delenv("LIGHTOS_OUTPUT_IFACE", raising=False)
    assert oi.output_interface_ip() is None


def test_iface_ip_from_env(monkeypatch):
    monkeypatch.setenv("LIGHTOS_OUTPUT_IFACE", IFACE)
    assert oi.output_interface_ip() == IFACE


@pytest.mark.parametrize("val", ["", "   ", "\t"])
def test_iface_ip_blank_is_none(monkeypatch, val):
    monkeypatch.setenv("LIGHTOS_OUTPUT_IFACE", val)
    assert oi.output_interface_ip() is None


# ── bind_to_output_iface ─────────────────────────────────────────────────────

def test_bind_noop_when_unset(monkeypatch):
    monkeypatch.delenv("LIGHTOS_OUTPUT_IFACE", raising=False)
    s = _FakeSock()
    assert oi.bind_to_output_iface(s) is False
    assert s.bound is None


def test_bind_uses_iface_ip(monkeypatch):
    monkeypatch.setenv("LIGHTOS_OUTPUT_IFACE", IFACE)
    s = _FakeSock()
    assert oi.bind_to_output_iface(s) is True
    assert s.bound == (IFACE, 0)


def test_bind_swallows_oserror(monkeypatch):
    monkeypatch.setenv("LIGHTOS_OUTPUT_IFACE", IFACE)

    class _Bad(_FakeSock):
        def bind(self, addr):
            raise OSError("iface weg / falsche IP")

    assert oi.bind_to_output_iface(_Bad()) is False   # geschluckt, kein Throw


# ── set_multicast_iface ──────────────────────────────────────────────────────

def test_multicast_iface_noop_when_unset(monkeypatch):
    monkeypatch.delenv("LIGHTOS_OUTPUT_IFACE", raising=False)
    s = _FakeSock()
    assert oi.set_multicast_iface(s) is False
    assert s.opts == []


def test_multicast_iface_sets_option(monkeypatch):
    monkeypatch.setenv("LIGHTOS_OUTPUT_IFACE", IFACE)
    s = _FakeSock()
    assert oi.set_multicast_iface(s) is True
    assert (_socket.IPPROTO_IP, _socket.IP_MULTICAST_IF,
            _socket.inet_aton(IFACE)) in s.opts


# ── Integration: die Sender binden tatsächlich ───────────────────────────────

def test_artnet_sender_binds_iface(monkeypatch):
    from src.core.dmx import artnet
    monkeypatch.setenv("LIGHTOS_OUTPUT_IFACE", IFACE)
    fake = _FakeSock()
    monkeypatch.setattr(artnet.socket, "socket", lambda *a, **k: fake)
    artnet.ArtNetSender()
    assert fake.bound == (IFACE, 0)


def test_artnet_sender_default_no_bind(monkeypatch):
    from src.core.dmx import artnet
    monkeypatch.delenv("LIGHTOS_OUTPUT_IFACE", raising=False)
    fake = _FakeSock()
    monkeypatch.setattr(artnet.socket, "socket", lambda *a, **k: fake)
    artnet.ArtNetSender()
    assert fake.bound is None   # Default: kein Bind, OS-Routing unverändert


def test_sacn_sender_multicast_sets_iface(monkeypatch):
    from src.core.dmx import sacn
    monkeypatch.setenv("LIGHTOS_OUTPUT_IFACE", IFACE)
    fake = _FakeSock()
    monkeypatch.setattr(sacn.socket, "socket", lambda *a, **k: fake)
    sacn.SACNSender(target_ip=None)   # None = Multicast
    assert (_socket.IPPROTO_IP, _socket.IP_MULTICAST_IF,
            _socket.inet_aton(IFACE)) in fake.opts
    assert fake.bound == (IFACE, 0)
