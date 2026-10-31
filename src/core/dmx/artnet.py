"""Art-Net 4 UDP Sender."""
import socket
import struct

ARTNET_PORT = 6454
ARTNET_HEADER = b"Art-Net\x00"
OPCODE_DMX = 0x5000
ARTNET_VERSION = 14

#: OUT-79: Quell-Ports der eigenen Sender. Der Art-Net-Eingang bekommt die
#: eigene Broadcast-Ausgabe zurück (das System liefert Broadcasts auch lokal
#: aus) — die darf nicht als „es kommt etwas an“ zählen, sonst schwiege der
#: Firewall-Hinweis gerade im Normalfall (Ausgabe an, Pult blockiert).
_eigene_quellports: set[int] = set()


def eigene_quellports() -> frozenset:
    return frozenset(_eigene_quellports)


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
    #: STAB-39: True = ohne echte App, es geht nichts ins Netz.
    _stumm = False

    def __init__(self, target_ip: str = "255.255.255.255"):
        from src.core.paths import echte_ausgabe_pruefen
        self._stumm = not echte_ausgabe_pruefen("Art-Net")
        # NET-04: Steht als Ziel der LIMITED Broadcast (255.255.255.255) UND ist
        # eine Ausgangs-NIC gewaehlt, geht es an deren GERICHTETEN Broadcast
        # (z. B. 192.0.2.255). Limited Broadcast wird von Routern nicht
        # weitergereicht und unter Linux nur ueber die Default-Route gesendet —
        # auf einem Venue-PC mit Lichtnetz an der zweiten NIC verpufft er
        # lautlos. Ein ausdruecklich eingetragenes Unicast-/Broadcast-Ziel bleibt
        # unangetastet, und OHNE gewaehlte NIC aendert sich gar nichts.
        if target_ip == "255.255.255.255":
            from src.core.dmx.output_iface import artnet_broadcast_target
            target_ip = artnet_broadcast_target(target_ip)
        self.target_ip = target_ip
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # XPLAT-06: optional an eine gewählte Ausgangs-NIC binden (LIGHTOS_OUTPUT_IFACE)
        # -> Broadcast geht über dieses Interface (Linux Multi-NIC). No-op im Default.
        from src.core.dmx.output_iface import bind_to_output_iface
        bind_to_output_iface(self._sock)
        self._sequence = 0
        self._quellport: int | None = None

    def send_dmx(self, universe: int, data: bytes):
        """Sendet ein ArtDmx Paket. universe = 0-32767, data = 2-512 Bytes."""
        if self._stumm:
            return
        self._sequence = (self._sequence % 255) + 1
        packet = _build_artdmx(universe, data, self._sequence)
        if self._quellport is None:
            self._quellport_merken()
        self._sock.sendto(packet, (self.target_ip, ARTNET_PORT))

    def _quellport_merken(self):
        """Quell-Port VOR dem ersten Senden festlegen und merken — für den
        Echo-Filter des Eingangs (OUT-79). Ohne eigene Bindung vergibt das
        System den Port erst in ``sendto``; der Eingang konnte das erste Paket
        dann sehen, bevor der Port eingetragen war (unter Last gemessen). Die
        Bindung an ('', 0) ist genau die, die ``sendto`` sonst implizit macht."""
        try:
            try:
                port = int(self._sock.getsockname()[1])
            except OSError:
                # Windows: getsockname() auf einem noch ungebundenen UDP-Socket
                # wirft WinError 10022 (WSAEINVAL) statt Port 0 zu melden.
                port = 0
            if not port:
                self._sock.bind(("", 0))
                port = int(self._sock.getsockname()[1])
        except (OSError, TypeError, ValueError, IndexError):
            return
        if port:
            self._quellport = port
            _eigene_quellports.add(port)

    def close(self):
        if self._quellport is not None:
            _eigene_quellports.discard(self._quellport)
            self._quellport = None
        self._sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
