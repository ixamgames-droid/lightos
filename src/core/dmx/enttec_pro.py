"""Enttec DMX USB Pro — Ausgabe via pyserial."""
import serial
import serial.tools.list_ports

ENTTEC_VID = 0x0403
ENTTEC_PID = 0x6001
ENTTEC_BAUD = 57600
START_OF_MSG = 0x7E
END_OF_MSG = 0xE7
LABEL_DMX_OUTPUT = 6


def find_enttec_port() -> str | None:
    """Sucht automatisch nach einem Enttec Pro anhand VID/PID."""
    for port in serial.tools.list_ports.comports():
        if port.vid == ENTTEC_VID and port.pid == ENTTEC_PID:
            return port.device
    return None


def list_serial_ports() -> list[str]:
    """Gibt alle verfügbaren COM-Ports zurück."""
    return [p.device for p in serial.tools.list_ports.comports()]


def _build_packet(dmx_data: bytes) -> bytes:
    payload = bytes([0x00]) + dmx_data  # Start Code + DMX Daten
    length = len(payload)
    return bytes([
        START_OF_MSG,
        LABEL_DMX_OUTPUT,
        length & 0xFF,
        (length >> 8) & 0xFF,
        *payload,
        END_OF_MSG,
    ])


class EnttecPro:
    def __init__(self, port: str):
        self.port = port
        self._ser = serial.Serial(port, ENTTEC_BAUD, timeout=1)

    def send_dmx(self, dmx_data: bytes):
        """Sendet 512 Bytes DMX-Daten an den Enttec Pro."""
        assert len(dmx_data) == 512
        packet = _build_packet(dmx_data)
        self._ser.write(packet)

    def is_open(self) -> bool:
        return self._ser.is_open

    def close(self):
        if self._ser.is_open:
            self._ser.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
