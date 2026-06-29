"""STAB-08: Prozess-isolierte Enttec-Serial-Ausgabe.

Drei Ebenen, ohne die Suite mit echten Subprozessen zu fluten:
1. Worker-Sende-Schleife (`_serial_worker_loop`) — rein in-Prozess, alles injizierbar.
2. Parent-Proxy (`EnttecProcessProxy`) — mit Fake-Prozess-Fabrik (kein Spawn).
3. EIN echter Spawn-Smoke-Test: bogus Port -> Worker bleibt am Leben, meldet
   ST_DISABLED, sauberes close().
"""
from __future__ import annotations
import ctypes
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.serial_process import (
    EnttecProcessProxy, _serial_worker_loop, ST_OK, ST_DISABLED, ST_CONNECTING, DMX_BYTES,
)


# ── Stubs ─────────────────────────────────────────────────────────────────────

class _Flag:
    def __init__(self, v=0):
        self.value = v


class _StubDev:
    def __init__(self, disabled=False):
        self.sent: list[bytes] = []
        self._disabled = disabled
        self.closed = False

    def send_dmx(self, data):
        self.sent.append(bytes(data))

    def is_disabled(self):
        return self._disabled

    def close(self):
        self.closed = True


class _FakeProc:
    def __init__(self, alive=True):
        self._alive = alive
        self.started = False
        self.joins: list = []
        self.terminated = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        self.joins.append(timeout)

    def terminate(self):
        self.terminated = True
        self._alive = False


def _buf_with(pattern: bytes):
    buf = mp.Array("B", DMX_BYTES)
    ctypes.memmove(buf.get_obj(), pattern, DMX_BYTES)
    return buf


# ── 1) Worker-Schleife ────────────────────────────────────────────────────────

def test_worker_loop_sends_latest_buffer_and_sets_status():
    pattern = bytes((i % 256 for i in range(DMX_BYTES)))
    buf = _buf_with(pattern)
    dev = _StubDev()
    stop = _Flag(0)
    status = _Flag(ST_CONNECTING)
    _serial_worker_loop(lambda: dev, buf, stop, status,
                        frame_interval=0.0,
                        sleep=lambda _t: stop.__setattr__("value", 1),
                        clock=lambda: 0.0)
    assert dev.sent == [pattern], "Worker sendet das aktuelle 512-Byte-Frame"
    assert status.value == ST_OK


def test_worker_loop_reports_disabled_status():
    buf = _buf_with(bytes(DMX_BYTES))
    dev = _StubDev(disabled=True)
    stop = _Flag(0)
    status = _Flag(ST_CONNECTING)
    _serial_worker_loop(lambda: dev, buf, stop, status, frame_interval=0.0,
                        sleep=lambda _t: stop.__setattr__("value", 1),
                        clock=lambda: 0.0)
    assert status.value == ST_DISABLED


def test_worker_loop_retries_open_then_succeeds():
    buf = _buf_with(bytes(DMX_BYTES))
    dev = _StubDev()
    stop = _Flag(0)
    status = _Flag(ST_CONNECTING)
    calls = {"factory": 0, "sleep": 0}
    clk = {"t": 0.0}

    def factory():
        calls["factory"] += 1
        if calls["factory"] == 1:
            raise RuntimeError("port not there yet")
        return dev

    def sleep(_t):
        calls["sleep"] += 1
        clk["t"] += 1.0          # Drossel-Zeit (open_retry_s=1.0) ueberschreiten
        if calls["sleep"] >= 2:  # 1x fehlgeschlagenes Open, 1x Erfolg+Send -> stop
            stop.value = 1

    _serial_worker_loop(factory, buf, stop, status, frame_interval=0.0,
                        sleep=sleep, clock=lambda: clk["t"], open_retry_s=1.0)
    assert calls["factory"] == 2, "Open wird nach Fehlschlag gedrosselt erneut versucht"
    assert len(dev.sent) >= 1, "nach erfolgreichem Open wird gesendet"
    assert status.value == ST_OK


def test_worker_loop_closes_dev_on_stop():
    buf = _buf_with(bytes(DMX_BYTES))
    dev = _StubDev()
    stop = _Flag(0)
    status = _Flag(ST_CONNECTING)
    _serial_worker_loop(lambda: dev, buf, stop, status, frame_interval=0.0,
                        sleep=lambda _t: stop.__setattr__("value", 1),
                        clock=lambda: 0.0)
    assert dev.closed, "Worker schliesst das Geraet beim Stop"


# ── 2) Parent-Proxy (Fake-Prozess) ─────────────────────────────────────────────

def _proxy_with_proc(proc, clock=None):
    holder = {"p": proc}
    kwargs = {"_process_factory": lambda: holder["p"]}
    if clock is not None:
        kwargs["_clock"] = clock
    px = EnttecProcessProxy("COM_FAKE", **kwargs)
    return px, holder


def test_proxy_publishes_frame_to_shared_buffer():
    px, _ = _proxy_with_proc(_FakeProc(alive=True))
    try:
        pattern = bytes(((i * 7) % 256 for i in range(DMX_BYTES)))
        px.send_dmx(pattern)
        assert bytes(px._buf.get_obj()) == pattern
    finally:
        px._closed = True  # close() wuerde den Fake nur joinen; Buffer reicht


def test_proxy_respawns_dead_worker_throttled():
    spawns = {"n": 0}
    clk = {"t": 100.0}

    def factory():
        spawns["n"] += 1
        return _FakeProc(alive=False)   # Worker sofort "tot"

    px = EnttecProcessProxy("COM_FAKE", _process_factory=factory,
                            _clock=lambda: clk["t"])
    assert spawns["n"] == 1, "ein Spawn beim Konstruieren"
    # Direkt danach (innerhalb RESPAWN_EVERY_S) -> KEIN Respawn
    px.send_dmx(bytes(DMX_BYTES))
    assert spawns["n"] == 1, "innerhalb der Drossel kein Respawn"
    # Uhr ueber die Drossel hinaus -> Respawn
    clk["t"] += px.RESPAWN_EVERY_S + 0.1
    px.send_dmx(bytes(DMX_BYTES))
    assert spawns["n"] == 2, "nach Drossel-Zeit wird der tote Worker respawnt"


def test_proxy_close_terminates_living_worker():
    proc = _FakeProc(alive=True)
    px, _ = _proxy_with_proc(proc)
    px.close()
    assert proc.joins, "close() joint den Worker"
    assert proc.terminated, "lebt er nach Join noch -> terminate()"
    assert px.is_open() is False, "nach close() gilt der Proxy als zu"
    # idempotent
    px.close()


def test_proxy_is_disabled_reflects_status():
    px, _ = _proxy_with_proc(_FakeProc(alive=True))
    try:
        px._status.value = ST_DISABLED
        assert px.is_disabled() is True
        px._status.value = ST_OK
        assert px.is_disabled() is False
    finally:
        px._closed = True


def test_proxy_send_noop_after_close():
    proc = _FakeProc(alive=True)
    px, _ = _proxy_with_proc(proc)
    px.close()
    # darf nicht crashen / nichts publizieren
    px.send_dmx(bytes(DMX_BYTES))


# ── 3) Echter Spawn-Smoke-Test ─────────────────────────────────────────────────

def test_real_spawn_with_unopenable_port_stays_alive_and_disables():
    """Echter Subprozess: bogus Port -> Worker bleibt am Leben (Open-Retry), meldet
    ST_DISABLED. Validiert Spawn + Import-Sicherheit des Workers + sauberes close()."""
    px = EnttecProcessProxy("COM_LIGHTOS_DOES_NOT_EXIST")
    try:
        assert px.is_open(), "Worker-Prozess laeuft kurz nach Spawn"
        # Auf das Disabled-Signal warten (Open eines bogus Ports schlaegt schnell fehl).
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not px.is_disabled():
            time.sleep(0.05)
        assert px.is_disabled(), "nicht oeffenbarer Port -> Worker meldet ST_DISABLED"
        assert px.is_open(), "Worker stirbt NICHT an einem Open-Fehler (nur Respawn bei Crash)"
    finally:
        px.close()
    assert px.is_open() is False, "nach close() ist der Worker beendet"
