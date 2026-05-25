# Art-Net 4 — Protokoll-Implementierung

## Überblick

Art-Net ist ein UDP-basiertes Protokoll zur Übertragung von DMX512-Daten über Ethernet oder WLAN. Es ist industriestandard und wird von nahezu allen professionellen DMX-Nodes, Dimmern und Effektgeräten unterstützt.

| Parameter | Wert |
|-----------|------|
| Protokoll | UDP/IP |
| Port | 6454 (0x1936) |
| Max. Universen | 32.768 (Art-Net 4) |
| Datengröße | 512 Bytes pro Paket |
| Refresh-Empfehlung | max. 44 Hz |
| Broadcast-Adresse | 2.255.255.255 oder Subnetz-Broadcast |

---

## Art-Net Paket-Typen

| OpCode | Name | Beschreibung |
|--------|------|-------------|
| 0x5000 | ArtDmx | DMX-Daten senden (Hauptpaket) |
| 0x2000 | ArtPoll | Andere Nodes im Netzwerk suchen |
| 0x2100 | ArtPollReply | Antwort auf ArtPoll |
| 0x6000 | ArtSync | Alle Nodes synchron ausgeben |
| 0x5800 | ArtNzs | Non-Zero Start Code DMX |

---

## ArtDmx Paket-Struktur

```
Offset | Bytes | Inhalt
-------|-------|-------
0      | 8     | ID = "Art-Net\0" (ASCII)
8      | 2     | OpCode = 0x5000 (Little Endian)
10     | 2     | ProtVer = 14 (Big Endian, High byte first)
12     | 1     | Sequence (0 = disabled, 1-255 = Paketzähler)
13     | 1     | Physical (physischer Input-Port, meist 0)
14     | 2     | PortAddress (Universe-Nummer, Little Endian)
16     | 2     | Length (Anzahl DMX-Bytes, Big Endian, min 2, max 512)
18     | N     | Data (DMX-Kanal 1 bis N)
```

### PortAddress Berechnung
```
PortAddress = (Net << 8) | (SubNet << 4) | Universe
```
- **Net**: 0–127 (7 Bit)
- **SubNet**: 0–15 (4 Bit)
- **Universe**: 0–15 (4 Bit)

Beispiel: Net=0, SubNet=0, Universe=0 → PortAddress = 0x0000

---

## Python-Implementierung

```python
import socket
import struct

ARTNET_PORT = 6454
ARTNET_HEADER = b"Art-Net\x00"
ARTNET_OPCODE_DMX = 0x5000
ARTNET_VERSION = 14

class ArtNetSender:
    def __init__(self, target_ip: str = "2.255.255.255"):
        self.target_ip = target_ip
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sequence = 0

    def send_dmx(self, universe: int, data: bytes):
        """Sendet ein ArtDmx-Paket für ein Universe."""
        assert 0 <= universe <= 32767
        assert 1 <= len(data) <= 512

        self.sequence = (self.sequence % 255) + 1
        length = len(data)

        packet = (
            ARTNET_HEADER
            + struct.pack("<H", ARTNET_OPCODE_DMX)   # OpCode LE
            + struct.pack(">H", ARTNET_VERSION)       # Version BE
            + bytes([self.sequence, 0])               # Sequence, Physical
            + struct.pack("<H", universe)             # PortAddress LE
            + struct.pack(">H", length)               # Length BE
            + data
        )
        self.sock.sendto(packet, (self.target_ip, ARTNET_PORT))

    def close(self):
        self.sock.close()
```

---

## Art-Net Node Discovery (ArtPoll)

```python
ARTNET_OPCODE_POLL = 0x2000

def send_artpoll(sock: socket.socket):
    """Sendet ArtPoll Broadcast zum Auffinden von Nodes."""
    packet = (
        ARTNET_HEADER
        + struct.pack("<H", ARTNET_OPCODE_POLL)
        + struct.pack(">H", ARTNET_VERSION)
        + bytes([0x02, 0x00])  # TalkToMe: Reply on change
    )
    sock.sendto(packet, ("255.255.255.255", ARTNET_PORT))
```

---

## Mehrere Universen über Art-Net

LightOS unterstützt bis zu **16 Art-Net Universen** gleichzeitig (erweiterbar):

```
Universe 0  →  PortAddress 0x0000  →  ArtDmx Paket
Universe 1  →  PortAddress 0x0001  →  ArtDmx Paket
Universe 2  →  PortAddress 0x0002  →  ArtDmx Paket
...
Universe 15 →  PortAddress 0x000F  →  ArtDmx Paket
```

---

## Netzwerk-Einstellungen

### Empfohlene IP-Konfiguration
Art-Net ist für das **2.x.x.x / 10.x.x.x** Subnetz ausgelegt:

| Setting | Wert |
|---------|------|
| IP-Adresse (PC) | 2.x.x.x oder 10.x.x.x |
| Subnetzmaske | 255.0.0.0 |
| Broadcast | 2.255.255.255 |

> Hinweis: Art-Net funktioniert auch in normalen Heimnetzwerken (192.168.x.x), manche Nodes benötigen aber 2.x.x.x.

### WLAN-Kompatibilität
Art-Net über WLAN ist möglich, aber für kritische Live-Einsätze wird Kabel (Ethernet) empfohlen. Snapdragon-Geräte mit Wi-Fi 6E haben ausreichend geringe Latenz für die meisten Anwendungen.

---

## Art-Net Receive (Node-Modus)

LightOS kann auch Art-Net **empfangen** (z.B. von GrandMA oder ChamSys als Backup oder Merge):

```python
class ArtNetReceiver:
    def __init__(self, callback):
        self.callback = callback  # fn(universe: int, data: bytes)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", ARTNET_PORT))
        self.sock.setblocking(False)

    def receive_loop(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(600)
                self._parse(data)
            except BlockingIOError:
                pass

    def _parse(self, raw: bytes):
        if not raw.startswith(ARTNET_HEADER):
            return
        opcode = struct.unpack_from("<H", raw, 8)[0]
        if opcode == ARTNET_OPCODE_DMX:
            universe = struct.unpack_from("<H", raw, 14)[0]
            length = struct.unpack_from(">H", raw, 16)[0]
            dmx_data = raw[18:18 + length]
            self.callback(universe, dmx_data)
```
