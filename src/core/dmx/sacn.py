"""sACN / E1.31 Output — Streaming ACN (ANSI E1.31)."""
from __future__ import annotations
import socket
import struct
import time
import uuid

SACN_PORT = 5568
SACN_MULTICAST_BASE = "239.255.0."

# E1.31 packet offsets per spec
_PREAMBLE = bytes([
    0x00, 0x10,             # Preamble size
    0x00, 0x00,             # Postamble size
    0x41, 0x53, 0x43, 0x2d,
    0x45, 0x31, 0x2e, 0x31,
    0x37, 0x00, 0x00, 0x00, # ACN Packet Identifier
])


def _pack_framing(data: bytes, universe: int, seq: int, source: str, cid: bytes) -> bytes:
    """Build a complete sACN (E1.31) packet for one universe."""
    # DMP layer (with 513-byte property block: startcode 0x00 + 512 DMX bytes)
    dmp_flags = 0x70A0 | (len(data) + 11)
    dmp_layer = struct.pack(
        "!HBHHHB",
        dmp_flags,   # Flags+Length (DMP layer)
        0x02,        # Vector: DMP_VECTOR_SET_PROPERTY
        0xA100,      # Address type + first property addr
        0x0001,      # Address increment
        len(data) + 1,  # Property count
        0x00,        # Start code
    ) + data

    # Framing layer
    source_enc = source.encode("utf-8")[:64].ljust(64, b"\x00")
    fl_flags = 0x70000000 | (len(dmp_layer) + 77)
    fl_layer = struct.pack(
        "!IBBB64sBBH",
        fl_flags,
        0x00000002,   # E1.31 vector
        0x00, 0x00,   # reserved
        source_enc,
        0x64,         # Priority
        0x00,         # Synchronization address
        seq & 0xFF,   # Sequence
    ) + struct.pack("!BH", 0x00, universe) + dmp_layer

    # Root layer
    pdu_len = len(fl_layer) + len(_PREAMBLE) + 6
    root_flags = 0x70000000 | pdu_len
    root_layer = (
        _PREAMBLE
        + cid
        + struct.pack("!I", root_flags | 0x00000004)
        + fl_layer
    )
    return root_layer


class SACNSender:
    """Sends sACN (E1.31) DMX data over UDP multicast or unicast."""

    def __init__(self, target_ip: str | None = None, source_name: str = "LightOS"):
        self._target_ip = target_ip   # None = multicast
        self._source_name = source_name
        self._cid = uuid.uuid4().bytes
        self._sock: socket.socket | None = None
        self._seq: dict[int, int] = {}   # universe → seq counter
        self._open()

    def _open(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self._target_ip is None:
            # Enable multicast
            self._sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 8
            )

    def send_dmx(self, universe: int, data: bytes):
        """Send 512 bytes of DMX data for the given universe (1-based)."""
        if self._sock is None:
            return
        # Pad or trim to exactly 512 bytes
        dmx = (data + bytes(512))[:512]
        seq = self._seq.get(universe, 0)
        self._seq[universe] = (seq + 1) & 0xFF

        try:
            packet = _pack_framing(dmx, universe, seq, self._source_name, self._cid)
        except struct.error:
            return

        if self._target_ip:
            dest = (self._target_ip, SACN_PORT)
        else:
            dest = (f"{SACN_MULTICAST_BASE}{universe}", SACN_PORT)

        try:
            self._sock.sendto(packet, dest)
        except OSError:
            pass

    def close(self):
        if self._sock:
            self._sock.close()
            self._sock = None
