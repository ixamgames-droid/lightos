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
        # write_timeout ist KRITISCH: ohne ihn blockiert _ser.write() endlos,
        # wenn das Geraet nicht abnimmt (falscher Port / abgezogen / kein echter
        # Enttec). Da Render+Senden im selben 44-Hz-Thread laufen, wuerde das die
        # GESAMTE Engine einfrieren. 0.5 s sind grosszuegig fuer ein 513-Byte-
        # Paket bei 57600 Baud (~90 ms); ein Timeout wirft SerialTimeoutException,
        # die der OutputManager faengt und das Frame ueberspringt.
        self._ser = serial.Serial(port, ENTTEC_BAUD, timeout=1, write_timeout=0.5)

    def send_dmx(self, dmx_data: bytes):
        """Sendet 512 Bytes DMX-Daten an den Enttec Pro."""
        assert len(dmx_data) == 512
        # Port wurde evtl. gerade (Reconnect/Shutdown) geschlossen -> NICHT auf
        # einem toten Handle schreiben: das loest unter Windows eine native Access
        # Violation aus statt einer fangbaren Python-Exception.
        if not self._ser.is_open:
            return
        packet = _build_packet(dmx_data)
        try:
            self._ser.write(packet)
        except serial.SerialTimeoutException:
            # Geraet nimmt gerade nicht ab -> Frame verwerfen, naechstes Frame
            # versucht es erneut. NICHT blockieren.
            try:
                self._ser.reset_output_buffer()
            except Exception:
                pass
        except (serial.SerialException, OSError, ValueError):
            # Port wurde mitten im Senden geschlossen/abgezogen -> Frame verwerfen,
            # nicht propagieren (sonst beendet sich der Output-Thread bzw. crasht).
            pass

    def is_open(self) -> bool:
        return self._ser.is_open

    def close(self):
        """Schliesst den Port. Vorher den Output-Puffer abbrechen/leeren — sonst kann
        CloseHandle() unter Windows mit einem noch ausstehenden WriteFile kollidieren
        (Access Violation beim Beenden, crash.log 22.06.). Idempotent + fehlertolerant."""
        if not self._ser.is_open:
            return
        try:
            self._ser.reset_output_buffer()
        except Exception:
            pass
        try:
            self._ser.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
