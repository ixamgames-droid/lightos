# DMX512 & Enttec Pro — Protokoll-Dokumentation

## DMX512 Grundlagen

DMX512 ist ein serielles Protokoll zur Steuerung von Bühnenlicht und Effekten.

| Parameter | Wert |
|-----------|------|
| Baudrate | 250.000 Baud |
| Kanäle pro Universe | 512 |
| Wert pro Kanal | 0–255 (uint8) |
| Refresh-Rate | max. 44 Hz (Standard ~30 Hz) |
| Frame-Länge | ~22,7 ms bei 44 Hz |

### DMX Frame Struktur
```
[BREAK] [MAB] [Start-Code=0x00] [CH1] [CH2] ... [CH512]
```
- **BREAK**: Mindestens 88 µs Low-Signal (Reset-Signal)
- **MAB** (Mark After Break): Mindestens 8 µs High
- **Start-Code**: 0x00 für Standard-Dimmer-Daten
- **Daten**: 512 Bytes (Kanäle 1–512)

---

## Enttec Pro USB Interface

Der **Enttec DMX USB Pro** ist ein USB-zu-DMX512-Konverter mit eigener Firmware.

### Technische Daten
| Parameter | Wert |
|-----------|------|
| Verbindung | USB 2.0 (VCP / Virtual COM Port) |
| Chip | FTDI FT232R |
| Windows-Treiber | FTDI VCP (bereits in Windows 10/11 integriert) |
| ARM64-Support | FTDI-Treiber für ARM64 verfügbar (Windows ARM) |
| USB VID/PID | 0x0403 / 0x6001 |
| Max. Baudrate (USB) | 12 Mbit/s |

### Enttec Pro Protokoll (USB Message Protocol)
Kommunikation über USB mit proprietärem Message-Format (nicht direkt DMX):

```
[0x7E] [Label] [DataLen_LSB] [DataLen_MSB] [Data...] [0xE7]
```

| Label | Beschreibung |
|-------|-------------|
| 0x03 | DMX Output senden (Send DMX Packet) |
| 0x06 | Programmierbarkeit ändern |
| 0x0A | Seriellen Baud-Rate Parameter setzen |
| 0x0D | Get Widget Parameters |

### DMX Senden (Label 0x03)
```python
# Paket-Aufbau für Enttec Pro
START_OF_MSG = 0x7E
DMX_SEND_LABEL = 6       # Label 6 = DMX Output
END_OF_MSG = 0xE7

def build_packet(dmx_data: bytes) -> bytes:
    # dmx_data: 512 Bytes (Kanäle 1-512)
    # Erster Byte ist immer 0x00 (Start Code)
    payload = bytes([0x00]) + dmx_data
    length = len(payload)
    return bytes([
        START_OF_MSG,
        DMX_SEND_LABEL,
        length & 0xFF,          # LSB
        (length >> 8) & 0xFF,   # MSB
        *payload,
        END_OF_MSG
    ])
```

### Python-Implementierung (pyserial)
```python
import serial
import serial.tools.list_ports

def find_enttec_port() -> str | None:
    """Findet den Enttec Pro automatisch anhand VID/PID."""
    for port in serial.tools.list_ports.comports():
        if port.vid == 0x0403 and port.pid == 0x6001:
            return port.device
    return None

class EnttecPro:
    BAUD = 57600  # Enttec Pro USB Baud

    def __init__(self, port: str):
        self.ser = serial.Serial(port, self.BAUD, timeout=1)

    def send_dmx(self, universe: bytes):
        """Sendet ein komplettes DMX-Universe (512 Bytes)."""
        assert len(universe) == 512
        packet = self._build_packet(universe)
        self.ser.write(packet)

    def close(self):
        self.ser.close()
```

---

## Enttec Open DMX USB (Alternate)

Das **Open DMX USB** (günstigere Version) hat keine eigene Firmware — der PC generiert das DMX-Timing selbst. Auf Windows ist das wegen des nicht-deterministischen Schedulings fehleranfällig.

**Empfehlung:** Enttec Pro verwenden. Open DMX wird als optionale Fallback-Implementierung unterstützt.

---

## ARM64 (Snapdragon) Kompatibilität

### FTDI Treiber auf Windows ARM
- FTDI bietet ARM64-kompatible VCP-Treiber an
- Windows 11 ARM enthält FTDI-Treiber bereits inbox (seit Build 22H2+)
- pyserial läuft nativ auf ARM64 (pure Python + Windows COMx)
- Kein x64-Emulations-Overhead für den seriellen Port

### Praxis-Hinweise
- Auf Snapdragon-Geräten: USB-A via USB-C Adapter
- COM-Port-Nummerierung identisch zu x64 Windows
- Treiber-Installation: Automatisch via Windows Update

---

## DMX Timing & Refresh-Loop

```python
import threading
import time

class DMXOutputLoop(threading.Thread):
    TARGET_HZ = 44
    FRAME_MS = 1000 / TARGET_HZ  # ~22.7 ms

    def __init__(self, sender):
        super().__init__(daemon=True)
        self.sender = sender
        self.universe = bytearray(512)
        self._running = False

    def run(self):
        self._running = True
        while self._running:
            t0 = time.perf_counter()
            self.sender.send_dmx(bytes(self.universe))
            elapsed = (time.perf_counter() - t0) * 1000
            sleep_ms = max(0, self.FRAME_MS - elapsed)
            time.sleep(sleep_ms / 1000)

    def stop(self):
        self._running = False
```

---

## Mehrere Universen

Enttec Pro unterstützt **1 Universe pro Gerät**. Für mehrere Universen:

| Option | Beschreibung |
|--------|-------------|
| Mehrere Enttec Pros | Ein Gerät pro Universe |
| Art-Net Node | Netzwerkbasiert, viele Universen |
| Enttec Pro Mk2 | Dual-Universe Version |

LightOS unterstützt alle drei Optionen gleichzeitig.
