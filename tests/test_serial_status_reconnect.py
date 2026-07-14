"""SERIAL-01 / SERIAL-02: wahrhaftiger Verbindungsstatus + Reconnect via VID/PID.

Ohne echte serielle Hardware (``serial.Serial`` / ``find_enttec_port`` werden per
Mock ersetzt, kein Prozess-Spawn):

SERIAL-01: Ein Worker mit totem/falschem COM-Port laeuft weiter und meldet
``ST_DISABLED``. Der Proxy darf dann NICHT "verbunden" melden — ``is_connected()``
False, ``status()`` == ``ST_DISABLED``, ``is_disabled()`` True. ``is_open()`` (reines
Prozess-Lebenszeichen) bleibt dabei bewusst True (Respawn-Kriterium).

SERIAL-02: Nach USB-Replug haengt der Enttec an einer NEUEN COM-Nummer. Der
Reconnect muss ihn per VID/PID (``find_enttec_port``) neu auffinden statt stur auf
der alten Nummer zu haengen; findet VID/PID nichts, Fallback auf die alte Nummer.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx import enttec_pro
from src.core.dmx.enttec_pro import EnttecPro
from src.core.dmx.serial_process import (
    EnttecProcessProxy, ST_OK, ST_DISABLED, ST_CONNECTING, DMX_BYTES,
)


# ── Fakes ──────────────────────────────────────────────────────────────────────

class _FakeProc:
    """Kein echter Subprozess — nur is_alive()/start()/join()/terminate()."""
    def __init__(self, alive=True):
        self._alive = alive

    def start(self):
        pass

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        pass

    def terminate(self):
        self._alive = False


def _proxy_with_alive_worker() -> EnttecProcessProxy:
    return EnttecProcessProxy("COM_TEST", _process_factory=lambda: _FakeProc(True))


class _FakeSerial:
    """Oeffnet nur Ports aus ``_available``; sonst SerialException (wie ein toter
    bzw. verschwundener COM-Port)."""
    _available: set[str] = set()

    def __init__(self, port, baud, timeout=1, write_timeout=0.5):
        if port not in _FakeSerial._available:
            raise enttec_pro.serial.SerialException(f"cannot open {port}")
        self.port = port
        self.is_open = True
        self.writes: list[bytes] = []

    def write(self, data):
        self.writes.append(bytes(data))

    def reset_output_buffer(self):
        pass

    def close(self):
        self.is_open = False


# ── SERIAL-01: totes Rig -> NICHT verbunden ─────────────────────────────────────

def test_disabled_worker_reports_not_connected():
    px = _proxy_with_alive_worker()
    try:
        # Worker meldet einen toten/falschen Port -> ST_DISABLED.
        px._status.value = ST_DISABLED
        assert px.is_disabled() is True
        assert px.status() == ST_DISABLED
        assert px.is_connected() is False, \
            "toter Port darf NICHT als verbunden gelten (SERIAL-01)"
        # is_open bleibt True: der Prozess lebt (Respawn-Kriterium), nur der Port ist tot.
        assert px.is_open() is True

        # Erstes Verbinden zaehlt ebenfalls nicht als verbunden.
        px._status.value = ST_CONNECTING
        assert px.is_connected() is False

        # Erst ST_OK == wirklich verbunden.
        px._status.value = ST_OK
        assert px.is_connected() is True
        assert px.is_disabled() is False
    finally:
        px._closed = True


def test_connected_requires_living_worker():
    # ST_OK, aber Prozess tot -> trotzdem nicht verbunden.
    px = EnttecProcessProxy("COM_TEST", _process_factory=lambda: _FakeProc(False))
    try:
        px._status.value = ST_OK
        assert px.is_connected() is False
    finally:
        px._closed = True


# ── SERIAL-02: Reconnect findet neue COM-Nummer ─────────────────────────────────

def test_reconnect_uses_find_enttec_port_on_new_com():
    _FakeSerial._available = {"COM3"}
    with mock.patch.object(enttec_pro.serial, "Serial", _FakeSerial):
        dev = EnttecPro("COM3")
        assert dev.port == "COM3"
        # Port gilt als tot; USB kommt unter NEUER Nummer zurueck.
        dev._disabled = True
        dev._last_reconnect = -1e9   # Drossel umgehen
        _FakeSerial._available = {"COM_NEW"}   # alte Nummer weg, neue da
        with mock.patch.object(enttec_pro, "find_enttec_port", lambda: "COM_NEW"):
            dev.send_dmx(bytes(512))   # loest _try_reconnect aus
        assert dev.port == "COM_NEW", "Reconnect uebernimmt die per VID/PID gefundene Nummer"
        assert dev.is_disabled() is False, "nach erfolgreichem Reopen wieder aktiv"
        assert dev._ser.is_open


def test_reconnect_falls_back_to_old_number_when_vidpid_absent():
    _FakeSerial._available = {"COM3"}
    with mock.patch.object(enttec_pro.serial, "Serial", _FakeSerial):
        dev = EnttecPro("COM3")
        dev._disabled = True
        dev._last_reconnect = -1e9
        # find_enttec_port findet nichts (Geraet noch nicht sichtbar) -> alte Nummer.
        with mock.patch.object(enttec_pro, "find_enttec_port", lambda: None):
            dev.send_dmx(bytes(512))
        assert dev.port == "COM3", "Fallback auf die urspruengliche Nummer"
        assert dev.is_disabled() is False
        assert dev._ser.is_open


def test_reconnect_stays_disabled_when_no_port_openable():
    _FakeSerial._available = {"COM3"}
    with mock.patch.object(enttec_pro.serial, "Serial", _FakeSerial):
        dev = EnttecPro("COM3")
        dev._disabled = True
        dev._last_reconnect = -1e9
        _FakeSerial._available = set()   # weder alt noch neu oeffenbar
        with mock.patch.object(enttec_pro, "find_enttec_port", lambda: None):
            dev.send_dmx(bytes(512))
        assert dev.is_disabled() is True, "kein Port offen -> bleibt disabled"
