"""Art-Net 4 UDP Sender."""
import socket
import struct

ARTNET_PORT = 6454
ARTNET_HEADER = b"Art-Net\x00"
OPCODE_DMX = 0x5000
ARTNET_VERSION = 14


def _build_artdmx(universe: int, data: bytes, sequence: int) -> bytes:
    length = len(data)
    return (
        ARTNET_HEADER
        + struct.pack("<H", OPCODE_DMX)
        + struct.pack(">H", ARTNET_VERSION)
        + bytes([sequence & 0xFF, 0])
        + struct.pack("<H", universe)
        + struct.pack(">H", length)
        + data
    )


class ArtNetSender:
    def __init__(self, target_ip: str = "2.255.255.255"):
        self.target_ip = target_ip
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sequence = 0

    def send_dmx(self, universe: int, data: bytes):
        """Sendet ein ArtDmx Paket. universe = 0-32767, data = 2-512 Bytes."""
        self._sequence = (self._sequence % 255) + 1
        packet = _build_artdmx(universe, data, self._sequence)
        self._sock.sendto(packet, (self.target_ip, ARTNET_PORT))

    def close(self):
        self._sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
