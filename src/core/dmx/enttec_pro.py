"""Enttec DMX USB Pro — Ausgabe via pyserial."""
import serial
import serial.tools.list_ports
import time

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
    # OUT-02: So viele aufeinanderfolgende Schreib-Fehler werten den Port als tot.
    # Danach NICHT weiter bei 44 Hz auf das (evtl. unter dem offenen Handle
    # entfernte) USB-Geraet schreiben — jeder WriteFile auf ein abgezogenes Geraet
    # riskiert eine native Access Violation, die KEIN Python-try/except faengt. Bei
    # wackligem Inline-USB-Stecker hammerte die Ausgabe sonst dauerhaft einen
    # sterbenden Port (Mit-Ursache der Serial-bezogenen Crashes, crash.log Jun 2026).
    FAIL_LIMIT = 20
    # Gedrosselter Reconnect-Versuch, solange der Port als tot gilt: kommt das USB
    # zurueck, reaktiviert sich die Ausgabe von selbst (ohne App-Neustart).
    RECONNECT_EVERY_S = 3.0

    def __init__(self, port: str):
        self.port = port
        # Fehler-Watchdog (OUT-02): zaehlt aufeinanderfolgende Schreib-Fehler; bei
        # FAIL_LIMIT wird der Port geschlossen und als tot markiert (_disabled).
        self._fail_count = 0
        self._disabled = False
        self._reconnect_every_s = self.RECONNECT_EVERY_S
        self._last_reconnect = 0.0
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
        # OUT-02: Gilt der Port als tot (zu viele Fehler in Folge), NICHT weiter
        # schreiben — nur gedrosselt einen Reconnect versuchen.
        if self._disabled:
            self._try_reconnect()
            return
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
            self._note_fail()
            try:
                self._ser.reset_output_buffer()
            except Exception:
                pass
            return
        except (serial.SerialException, OSError, ValueError):
            # Port wurde mitten im Senden geschlossen/abgezogen -> Frame verwerfen,
            # nicht propagieren (sonst beendet sich der Output-Thread bzw. crasht).
            self._note_fail()
            return
        # Erfolgreicher Frame -> Fehlerzaehler zuruecksetzen. So loest nur ein
        # ANHALTENDER Abriss das Auto-Disable aus, nicht ein einzelner Hickup.
        self._fail_count = 0

    def _note_fail(self):
        """OUT-02: Schreib-Fehler zaehlen; ab FAIL_LIMIT den Port als tot werten."""
        self._fail_count += 1
        if self._fail_count >= self.FAIL_LIMIT:
            self._disable()

    def _disable(self):
        """Port als tot markieren UND schliessen — stoppt das 44-Hz-Hammern auf ein
        abgezogenes/wackliges USB-Geraet (Access-Violation-Schutz). Idempotent."""
        self._disabled = True
        self._last_reconnect = self._now()
        try:
            self._ser.reset_output_buffer()
        except Exception:
            pass
        try:
            self._ser.close()
        except Exception:
            pass

    def _try_reconnect(self):
        """Gedrosselt (``_reconnect_every_s``) den Port neu oeffnen. Gelingt es, ist
        das USB wieder da -> Ausgabe reaktivieren. Schlaegt es fehl, bleibt der Port
        tot und der naechste Versuch kommt nach der Drossel-Zeit."""
        now = self._now()
        if (now - self._last_reconnect) < self._reconnect_every_s:
            return
        self._last_reconnect = now
        try:
            self._ser = serial.Serial(self.port, ENTTEC_BAUD, timeout=1,
                                      write_timeout=0.5)
        except (serial.SerialException, OSError, ValueError):
            return
        self._disabled = False
        self._fail_count = 0

    def is_disabled(self) -> bool:
        """True, wenn der Port nach zu vielen Schreib-Fehlern als tot gilt (OUT-02).
        Fuer UI/Status nutzbar ('DMX-Output verloren — USB?')."""
        return self._disabled

    @staticmethod
    def _now() -> float:
        return time.monotonic()

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
