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

LightOS kann auch Art-Net (und sACN) **empfangen** und die eingehenden Kanäle in ein
lokales Universum **mischen** (HTP / LTP / REPLACE) — etwa um ein anderes Pult als
Backup oder zusätzliche Quelle durch LightOS hindurchzureichen.

> **Klarstellung:** Das ist **reines DMX-Durchmischen**, keine Pult-Integration.
> Ein grandMA, ChamSys o. ä. steuert dabei keine Executoren, Cuelisten oder den
> Grand Master von LightOS — seine Werte landen nur als Kanalwerte in der Ausgabe.
> Wer LightOS vom Pult aus **bedienen** will, nutzt die
> [Fernsteuerung](#fernsteuerung-pult-bedient-lightos) weiter unten.

Prinzip des Empfängers (vereinfacht; die echte Umsetzung liegt in
`src/core/dmx/artnet_input.py` bzw. `sacn_input.py`):

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

---

## Fernsteuerung (Pult bedient LightOS)

Seit NET-15 können eingehende Art-Net- oder sACN-Kanäle LightOS **bedienen** — der
universelle Weg für jedes Pult und jedes Programm, das DMX übers Netz senden kann,
ohne MIDI.

**Einrichten:** *Ausgabe → Reiter „DMX Input" → Gruppe „Fernsteuerung"*. Je Zeile:
Quelle (Art-Net/sACN), eingehendes Universum, Kanal und Ziel. „Fernsteuerung aktiv"
anhaken, **Übernehmen** — die Zuordnung wird gespeichert und die nötigen Empfänger
starten (auch beim nächsten Programmstart, solange „aktiv" gespeichert ist).

| Ziel | Wirkung |
|---|---|
| Executor-Fader | Fader des Executors *n* (aktuelle Seite) = Kanalwert 0–255 → 0–100 % |
| Grand Master | Grand Master; Executoren mit Fader-Funktion „master" folgen (wie bei MIDI) |
| GO (Weiter) / Zurück / Stop | Taste des Executors *n*, ausgelöst über eine Schwelle |

**Fader wirken nur bei Änderung.** Ein DMX-Strom wiederholt jeden Wert rund 44-mal
pro Sekunde. Würde jeder Wert angewandt, überschriebe ein ruhig stehendes Pult jede
Bedienung desselben Faders in LightOS. Deshalb ist der erste empfangene Wert (nach
„Übernehmen", nach dem Start und nach einer Empfangspause von mehr als 2,5 s) nur die
Ausgangslage; erst wenn sich der Kanal bewegt, springt der Fader auf den Pultwert.
Das entspricht der MIDI-Zuordnung, die ebenfalls nur auf Bewegung reagiert und
ebenfalls kein Soft-Takeover (Abholen) kennt.

**GO per Schwelle:** Steigt der Kanal über die Schwelle (Standard 50 % = Wert 128),
löst die Taste **genau einmal** aus. Erst wenn er wieder unter *Schwelle − Hysterese*
fällt (Hysterese 10 %, also unter 102), ist sie erneut scharf. Ein Kanal, der um die
Schwelle wackelt, löst so nicht mehrfach aus. Steht der Kanal bei der Ausgangslage
schon oben, löst das nichts aus.

**Nicht in der Ausgabe:** Zugeordnete Kanäle werden **nicht** in die Ausgabe gemischt,
auch wenn auf demselben eingehenden Universum ein Merge eingerichtet ist — ein
GO-Kanal soll nicht nebenbei einen Dimmer steuern. Alle anderen Kanäle des
Universums mischen weiter wie eingestellt.

**Threads:** Der Empfang läuft in einem eigenen Thread (`ArtNet-In`/`sACN-In`). Er
erkennt dort nur, *was* passieren soll; angewandt wird im GUI-Thread (Queue +
Qt-Signal, `src/core/dmx/fernsteuerung.py`).

**Gespeichert** wird in `dmx_fernsteuerung.json` im App-Datenordner (eigene Datei;
`universes.json` bleibt unberührt, ältere Konfigurationen laden also unverändert):

```json
{
  "version": 1,
  "aktiv": true,
  "zuordnungen": [
    {"quelle": "artnet", "universum": 1, "kanal": 1, "ziel": "executor_fader",
     "executor": 1, "schwelle": 50, "hysterese": 10},
    {"quelle": "artnet", "universum": 1, "kanal": 2, "ziel": "executor_go",
     "executor": 1, "schwelle": 50, "hysterese": 10},
    {"quelle": "sacn", "universum": 5, "kanal": 10, "ziel": "grand_master",
     "executor": 1, "schwelle": 50, "hysterese": 10}
  ]
}
```

Ziele: `executor_fader`, `grand_master`, `executor_go`, `executor_back`,
`executor_stop`. Die Hysterese hat (noch) keine eigene Spalte im Dialog, wird aber
aus der Datei gelesen und beim Speichern beibehalten.

**Grenzen:** Executor-Ziele gelten für die gerade aktive Executor-Seite (wie bei MIDI).
Die Art-Net-Universumsnummer ist die von LightOS (1-basiert, Draht-Universum 0 = 1),
wie beim Merge. Wird die Fernsteuerung ausgeschaltet, laufen bereits gestartete
Empfänger weiter (sie können für den Merge gebraucht werden).

