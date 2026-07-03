"""Ether-Dream-DAC-Treiber (LAS-05) — offenes Punkt-Streaming-Protokoll.

Spez: https://ether-dream.com/protocol.html — TCP :7765 (Befehle + Punktdaten,
jede Nachricht wird mit ACK/NAK + 20-Byte-``dac_status`` beantwortet; beim
Verbinden schickt die DAC sofort eine Ping-Antwort) und UDP :7654
(Discovery-Broadcast, 1×/Sekunde). Alles Little-Endian, reine
``struct``/``socket``-Implementierung — testbar ohne Hardware über einen
Fake-DAC-Server (siehe tests/test_etherdream_protocol.py).

E-Stop ist im Protokoll First-Class (0x00 senden / 'c' zum Entriegeln) und
wird vom LaserOutputManager als harter Not-Aus genutzt.
"""
from __future__ import annotations

import socket
import struct
from dataclasses import dataclass

from .frame import LaserFrame

TCP_PORT = 7765
BROADCAST_PORT = 7654

# dac_point: control u16, x i16, y i16, r/g/b/i/u1/u2 u16 (18 Bytes).
_POINT = struct.Struct("<HhhHHHHHH")
# dac_status: protocol, light_engine_state, playback_state, source (je u8),
# light_engine_flags/playback_flags/source_flags/buffer_fullness (je u16),
# point_rate/point_count (je u32) -> 20 Bytes.
_STATUS = struct.Struct("<BBBBHHHHII")
# dac_broadcast: mac(6) + hw_rev u16 + sw_rev u16 + buffer_capacity u16 +
# max_point_rate u32 (Header 16 Bytes) + dac_status(20) -> 36 Bytes.
_BROADCAST_HEAD = struct.Struct("<6sHHHI")

ACK = ord("a")
NAK_FULL = ord("F")
NAK_INVALID = ord("I")
NAK_STOP = ord("!")

PLAYBACK_IDLE = 0
PLAYBACK_PREPARED = 1
PLAYBACK_PLAYING = 2
LIGHT_ENGINE_ESTOP = 3


class EtherDreamError(RuntimeError):
    """Protokoll-/Transportfehler (NAK, Timeout, kaputte Antwort)."""


@dataclass
class DacStatus:
    protocol: int
    light_engine_state: int
    playback_state: int
    source: int
    light_engine_flags: int
    playback_flags: int
    source_flags: int
    buffer_fullness: int
    point_rate: int
    point_count: int

    @property
    def estopped(self) -> bool:
        return self.light_engine_state == LIGHT_ENGINE_ESTOP


def parse_status(data: bytes) -> DacStatus:
    if len(data) < _STATUS.size:
        raise EtherDreamError(f"dac_status zu kurz: {len(data)} Bytes")
    return DacStatus(*_STATUS.unpack(data[:_STATUS.size]))


def parse_broadcast(data: bytes) -> dict:
    """UDP-Discovery-Paket → dict (mac als Hex-String, plus DacStatus)."""
    need = _BROADCAST_HEAD.size + _STATUS.size
    if len(data) < need:
        raise EtherDreamError(f"Broadcast zu kurz: {len(data)} Bytes")
    mac, hw_rev, sw_rev, buffer_capacity, max_point_rate = \
        _BROADCAST_HEAD.unpack(data[:_BROADCAST_HEAD.size])
    status = parse_status(data[_BROADCAST_HEAD.size:need])
    return {
        "mac": mac.hex(":"),
        "hw_rev": hw_rev,
        "sw_rev": sw_rev,
        "buffer_capacity": buffer_capacity,
        "max_point_rate": max_point_rate,
        "status": status,
    }


def discover(timeout: float = 1.5) -> list[dict]:
    """Lauscht kurz auf DAC-Broadcasts (jede DAC sendet 1×/Sekunde).
    Liefert dicts wie :func:`parse_broadcast` plus ``host``."""
    found: dict[str, dict] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        sock.bind(("", BROADCAST_PORT))
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, (host, _port) = sock.recvfrom(1024)
            except socket.timeout:
                break
            try:
                info = parse_broadcast(data)
            except EtherDreamError:
                continue
            info["host"] = host
            found[info["mac"]] = info
    except OSError:
        pass
    finally:
        sock.close()
    return list(found.values())


def encode_points(frame: LaserFrame) -> bytes:
    """LaserFrame → ``dac_point``-Bytes. Normierte Koordinaten (-1..+1) auf
    int16, Farben (0..1) auf u16; geblankte Punkte = Farbe/Intensität 0."""
    chunks = []
    for p in frame.points:
        x = max(-32768, min(32767, int(round(float(p.x) * 32767))))
        y = max(-32768, min(32767, int(round(float(p.y) * 32767))))
        if p.blanked:
            r = g = b = i = 0
        else:
            r = max(0, min(65535, int(round(float(p.r) * 65535))))
            g = max(0, min(65535, int(round(float(p.g) * 65535))))
            b = max(0, min(65535, int(round(float(p.b) * 65535))))
            i = max(r, g, b)
        chunks.append(_POINT.pack(0, x, y, r, g, b, i, 0, 0))
    return b"".join(chunks)


class EtherDreamConnection:
    """Eine TCP-Verbindung zu einer Ether-Dream-DAC.

    Nutzung: ``connect()`` → ``stream_frame(frame)`` pro Tick →
    ``stop()``/``estop()``/``close()``. Alle Befehle lesen synchron die
    22-Byte-Antwort; NAKs werfen :class:`EtherDreamError` (außer 'F'/Full
    beim Datenschreiben — das meldet ``stream_frame`` als ``False``)."""

    def __init__(self, host: str, port: int = TCP_PORT, timeout: float = 0.5):
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self._sock: socket.socket | None = None
        self.last_status: DacStatus | None = None

    # ── Transport ─────────────────────────────────────────────────────────
    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self):
        if self._sock is not None:
            return
        sock = socket.create_connection((self.host, self.port), self.timeout)
        sock.settimeout(self.timeout)
        self._sock = sock
        # Die DAC schickt beim Verbinden sofort eine Ping-Antwort.
        self._read_response(expect=ord("?"))

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock is not None
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise EtherDreamError("Verbindung geschlossen")
            buf += chunk
        return buf

    def _read_response(self, expect: int | None = None) -> tuple[int, DacStatus]:
        data = self._recv_exact(2 + _STATUS.size)
        resp, cmd = data[0], data[1]
        status = parse_status(data[2:])
        self.last_status = status
        if expect is not None and cmd != expect:
            raise EtherDreamError(
                f"Antwort auf falschen Befehl: {chr(cmd)!r} statt {chr(expect)!r}")
        return resp, status

    def _command(self, payload: bytes, expect_cmd: int,
                 allow_full: bool = False) -> tuple[int, DacStatus]:
        if self._sock is None:
            raise EtherDreamError("nicht verbunden")
        try:
            self._sock.sendall(payload)
            resp, status = self._read_response(expect=expect_cmd)
        except (OSError, socket.timeout) as e:
            self.close()
            raise EtherDreamError(f"Transportfehler: {e}") from e
        if resp == ACK:
            return resp, status
        if resp == NAK_FULL and allow_full:
            return resp, status
        raise EtherDreamError(
            f"NAK {chr(resp)!r} auf Befehl {chr(expect_cmd)!r} "
            f"(light_engine={status.light_engine_state}, "
            f"playback={status.playback_state})")

    # ── Befehle ───────────────────────────────────────────────────────────
    def ping(self) -> DacStatus:
        return self._command(b"?", ord("?"))[1]

    def prepare(self) -> DacStatus:
        return self._command(b"p", ord("p"))[1]

    def begin(self, point_rate: int, low_water_mark: int = 0) -> DacStatus:
        payload = b"b" + struct.pack("<HI", int(low_water_mark), int(point_rate))
        return self._command(payload, ord("b"))[1]

    def write_points(self, frame: LaserFrame) -> bool:
        """Punkte in den DAC-Puffer schreiben. ``False`` = Puffer voll
        (Frame verwerfen, kein Fehler)."""
        n = len(frame.points)
        if n == 0:
            return True
        payload = b"d" + struct.pack("<H", n) + encode_points(frame)
        resp, _status = self._command(payload, ord("d"), allow_full=True)
        return resp == ACK

    def stop(self) -> DacStatus:
        return self._command(b"s", ord("s"))[1]

    def estop(self) -> DacStatus:
        """Not-Aus: DAC hört sofort auf zu spielen, Shutter zu (falls
        verdrahtet); bleibt verriegelt bis :meth:`clear_estop`."""
        return self._command(b"\x00", 0x00)[1]

    def clear_estop(self) -> DacStatus:
        return self._command(b"c", ord("c"))[1]

    # ── Komfort: ein Frame pro Tick ───────────────────────────────────────
    def stream_frame(self, frame: LaserFrame) -> bool:
        """Frame in den Puffer schieben und die Wiedergabe sicherstellen.
        Rückgabe False, wenn der Puffer voll war (Frame übersprungen)."""
        self.connect()
        status = self.last_status
        if status is not None and status.estopped:
            return False
        if status is None or status.playback_state == PLAYBACK_IDLE:
            self.prepare()
        wrote = self.write_points(frame)
        status = self.last_status
        if (wrote and status is not None
                and status.playback_state != PLAYBACK_PLAYING):
            self.begin(point_rate=frame.pps)
        return wrote
