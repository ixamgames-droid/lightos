"""Enttec DMX USB Pro — Ausgabe via pyserial."""
import os
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


def port_is_foreign(port: str) -> bool:
    """True, wenn der Portname von einer ANDEREN Plattform stammt.

    Ein `COM3` auf Linux (oder ein `/dev/ttyUSB0` auf Windows) kann nicht bloss
    "gerade nicht da" sein — er kann auf diesem System gar nicht existieren.
    Der Unterschied ist wichtig fuer die Meldung: "Geraet abgezogen?" waere hier
    die falsche Fahrte, richtig ist "die Konfiguration stammt von einem anderen
    Rechner".
    """
    p = (port or "").strip()
    if not p:
        return False
    if os.name == "nt":
        return p.startswith("/dev/")
    return p.upper().startswith("COM")


def diagnose_port(configured: str) -> str | None:
    """Einen konfigurierten Enttec-Port begutachten. ``None`` = unauffaellig,
    sonst ein fertiger, dem Nutzer zeigbarer Satz mit konkretem Vorschlag.

    ★ Warum es das braucht (HW-5b): nach dem Umzug von Windows auf Linux stand in
    ``data/universes.json`` fuer das Enttec-Universe weiter ``"COM_FAKE"``. Auf
    Linux heisst dasselbe Geraet ``/dev/ttyUSB0``. ``EnttecPro("COM_FAKE")`` konnte
    also nur werfen, die Exception verschwand im ``except`` von
    ``apply_output_config`` — und der Statusbalken meldete trotzdem gruen
    „Enttec: /dev/ttyUSB0 OK", weil er nur die VID/PID-Anwesenheit prueft.
    Ergebnis: gar kein DMX, und nichts sagte es.

    **Bewusst nur Diagnose, kein automatisches Umbiegen.** Ein gefundener Adapter
    wird als *Vorschlag* genannt, nicht stillschweigend eingesetzt: an einem
    Rechner koennen mehrere FTDI-Geraete haengen, und DMX auf ein Geraet zu
    schicken, das der Nutzer nie konfiguriert hat, waere schlimmer als der
    ehrliche Hinweis. Ausserdem bliebe der Aufbau sonst davon abhaengig, was
    gerade eingesteckt ist — bis in die Tests hinein.

    (Das automatische Nachfinden per VID/PID gibt es weiterhin in
    ``EnttecPro._try_reconnect`` — dort aber fuer einen Port, der vorher schon
    funktioniert hat und mitten im Betrieb wegbricht. Anderer Fall, SERIAL-02.)
    """
    want = (configured or "").strip()
    try:
        vorhanden = list_serial_ports()
    except Exception:
        vorhanden = []
    if want and want in vorhanden:
        return None

    try:
        gefunden = find_enttec_port()
    except Exception:
        gefunden = None

    if not want:
        return ("Fuer dieses Universe ist kein Enttec-Port konfiguriert."
                + (f" Vorschlag: {gefunden} (per VID/PID gefunden)."
                   if gefunden else " Es ist auch keiner per VID/PID sichtbar."))

    grund = (f"Der konfigurierte Port {want!r} ist ein Portname von einer anderen "
             f"Plattform — die Konfiguration stammt vermutlich von einem anderen "
             f"Rechner."
             if port_is_foreign(want) else
             f"Der konfigurierte Port {want!r} existiert auf diesem System nicht.")
    if gefunden:
        return (f"{grund} Es geht kein DMX ueber diesen Adapter raus. "
                f"Vorschlag: im Universe-Manager auf {gefunden} umstellen "
                f"(dort per VID/PID als Enttec erkannt).")
    return (f"{grund} Es geht kein DMX ueber diesen Adapter raus, und es ist "
            f"auch kein Enttec per VID/PID sichtbar.")


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
        abgezogenes/wackliges USB-Geraet (Access-Violation-Schutz). Idempotent.

        OUT-51: **Das ist der Moment, in dem das Rig dunkel wird** — und bis
        hierhin passierte er lautlos. Die Meldung steht genau hier und nicht in
        ``_note_fail``, weil ``send_dmx`` bei gesetztem ``_disabled`` sofort
        aussteigt: dieser Zweig wird also einmal je Ausfall durchlaufen, nicht
        44 Mal pro Sekunde."""
        import sys
        print(f"[EnttecPro] Port {self.port} nach {self._fail_count} Schreib-"
              f"Fehlern in Folge deaktiviert — DMX geht hier nicht mehr raus. "
              f"Neuer Versuch alle {self._reconnect_every_s:g}s.", file=sys.stderr)
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
        tot und der naechste Versuch kommt nach der Drossel-Zeit.

        SERIAL-02: Nach einem USB-Replug haengt der Enttec oft an einer NEUEN
        COM-Nummer -> ein Reconnect nur auf die alte ``self.port`` heilte NIE. Darum
        zuerst per VID/PID neu auffinden (:func:`find_enttec_port`); nur wenn das
        nichts findet, Fallback auf die urspruengliche Nummer (mit Warnung)."""
        now = self._now()
        if (now - self._last_reconnect) < self._reconnect_every_s:
            return
        self._last_reconnect = now
        try:
            found = find_enttec_port()
        except Exception:
            found = None
        if found:
            if found != self.port:
                print(f"[EnttecPro] Reconnect: Enttec jetzt auf {found} "
                      f"(war {self.port}) — wechsle per VID/PID.")
            target = found
        else:
            # Kein Enttec per VID/PID sichtbar -> alte Nummer erneut versuchen.
            print(f"[EnttecPro] Reconnect: kein Enttec per VID/PID gefunden — "
                  f"Fallback auf alte Nummer {self.port}.")
            target = self.port
        try:
            self._ser = serial.Serial(target, ENTTEC_BAUD, timeout=1,
                                      write_timeout=0.5)
        except (serial.SerialException, OSError, ValueError):
            return
        self.port = target
        self._disabled = False
        self._fail_count = 0
        # OUT-51: Auch die Erholung gehoert gemeldet. Wer nur den Ausfall sieht,
        # sucht sonst weiter an einem Problem, das sich selbst behoben hat.
        import sys
        print(f"[EnttecPro] Port {target} wieder offen — DMX geht wieder raus.",
              file=sys.stderr)

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
