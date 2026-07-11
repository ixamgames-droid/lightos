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


# E1.31 / ACN vectors
_VECTOR_ROOT_E131_DATA = 0x00000004
_VECTOR_E131_DATA_PACKET = 0x00000002
_VECTOR_DMP_SET_PROPERTY = 0x02
_DMP_ADDR_DATA_TYPE = 0xA1   # 1-byte addressing, increment 1
_E131_DEFAULT_PRIORITY = 100
# OUT-06: Options-Bit 6 = "Stream_Terminated" (E1.31-2018 6.2.6). Beim close() 3x mit
# gesetztem Bit senden -> Empfaenger verwerfen die Quelle SOFORT, statt ~2,5 s auf den
# Network-Data-Loss-Timeout zu warten (haengende Kanaele beim Adapter-Wechsel).
_OPT_STREAM_TERMINATED = 0x40

# PDU-Flags: oberes Nibble 0x7 (Längen/Vector/Header-Flags gesetzt), die unteren
# 12 Bit tragen die PDU-Länge (inkl. des Flags+Length-Feldes selbst).
_PDU_FLAGS = 0x7000


def _pack_framing(data: bytes, universe: int, seq: int, source: str, cid: bytes,
                  options: int = 0x00) -> bytes:
    """Baut ein spec-konformes sACN-(E1.31-)Datenpaket fuer ein Universum.

    Layout (ANSI E1.31-2018) fuer 512 DMX-Kanaele = 638 Byte:
      Root-Layer   38B = Preamble/ACN-ID 16 + Flags&Len 2 + Vector 4 + CID 16
      Framing-Lay. 77B = Flags&Len 2 + Vector 4 + Source 64 + Prio 1 +
                          SyncAddr 2 + Seq 1 + Options 1 + Universe 2
      DMP-Layer   523B = Flags&Len 2 + Vector 1 + AddrType 1 + FirstAddr 2 +
                          AddrIncr 2 + PropCount 2 + (Startcode 1 + 512 DMX)
    """
    n = len(data)
    prop_count = n + 1                 # Startcode + DMX-Slots
    dmp_len = 10 + prop_count          # DMP-Header (10) + Property-Block
    framing_len = 77 + dmp_len         # Framing-Header (77) + DMP-PDU
    root_len = 22 + framing_len        # Flags&Len 2 + Vector 4 + CID 16 + Framing

    # Root-Layer
    root = bytearray()
    root += _PREAMBLE                                       # 16B Preamble + ACN-ID
    root += struct.pack("!H", _PDU_FLAGS | root_len)        # Flags & Length
    root += struct.pack("!I", _VECTOR_ROOT_E131_DATA)       # Vector (4B)
    root += cid                                             # CID (16B)

    # Framing-Layer
    source_enc = source.encode("utf-8")[:63].ljust(64, b"\x00")  # null-terminiert
    framing = bytearray()
    framing += struct.pack("!H", _PDU_FLAGS | framing_len)  # Flags & Length
    framing += struct.pack("!I", _VECTOR_E131_DATA_PACKET)  # Vector (4B)
    framing += source_enc                                   # Source Name (64B)
    framing += struct.pack("!B", _E131_DEFAULT_PRIORITY)    # Priority
    framing += struct.pack("!H", 0x0000)                    # Synchronization Address
    framing += struct.pack("!B", seq & 0xFF)                # Sequence Number
    framing += struct.pack("!B", options & 0xFF)            # Options
    framing += struct.pack("!H", universe & 0xFFFF)         # Universe

    # DMP-Layer
    dmp = bytearray()
    dmp += struct.pack("!H", _PDU_FLAGS | dmp_len)          # Flags & Length
    dmp += struct.pack("!B", _VECTOR_DMP_SET_PROPERTY)      # Vector (1B)
    dmp += struct.pack("!B", _DMP_ADDR_DATA_TYPE)           # Address & Data Type
    dmp += struct.pack("!H", 0x0000)                        # First Property Address
    dmp += struct.pack("!H", 0x0001)                        # Address Increment
    dmp += struct.pack("!H", prop_count)                    # Property Value Count
    dmp += b"\x00"                                          # DMX Start Code
    dmp += data                                             # DMX-Slots

    return bytes(root + framing + dmp)


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

        try:
            self._sock.sendto(packet, self._dest(universe))
        except OSError:
            pass

    def _dest(self, universe: int):
        if self._target_ip:
            return (self._target_ip, SACN_PORT)
        # E1.31 Multicast: 239.255.<Universe-High>.<Universe-Low>
        hi = (universe >> 8) & 0xFF
        lo = universe & 0xFF
        return (f"239.255.{hi}.{lo}", SACN_PORT)

    def close(self):
        if self._sock is None:
            return
        # OUT-06: E1.31-Stream-Termination — je zuletzt bespieltem Universum 3 Pakete
        # mit gesetztem Stream_Terminated-Options-Bit senden, damit Empfaenger die
        # Quelle sofort verwerfen (statt ~2,5 s Network-Data-Loss-Timeout). Ohne das
        # blieben beim Adapter-Wechsel kurz zwei Quellen aktiv (bekannte Merge-Luecke).
        for universe in list(self._seq.keys()):
            seq = self._seq.get(universe, 0)
            try:
                pkt = _pack_framing(bytes(512), universe, seq, self._source_name,
                                    self._cid, options=_OPT_STREAM_TERMINATED)
            except struct.error:
                continue
            dest = self._dest(universe)
            for _ in range(3):
                try:
                    self._sock.sendto(pkt, dest)
                except OSError:
                    break
        self._sock.close()
        self._sock = None
