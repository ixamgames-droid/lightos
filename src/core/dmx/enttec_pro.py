"""Enttec DMX USB Pro — Ausgabe via pyserial."""
import errno
import os
import serial
import serial.tools.list_ports
import threading
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


def enttec_kandidaten() -> list[tuple[str, str | None]]:
    """OUT-66: ALLE per VID/PID sichtbaren Enttec als ``(device, seriennummer)``.

    Die Seriennummer ist ``None``, wenn das System keine meldet. Anders als
    :func:`find_enttec_port` (erster Treffer) braucht der Reconnect die ganze
    Liste: bei zwei Dongles ist „der erste" oft der des anderen Universums."""
    out = []
    for port in serial.tools.list_ports.comports():
        if (getattr(port, "vid", None) == ENTTEC_VID
                and getattr(port, "pid", None) == ENTTEC_PID):
            sn = getattr(port, "serial_number", None)
            out.append((port.device, str(sn).strip() or None if sn else None))
    return out


def _port_key(port: str | None) -> str:
    """OUT-66: Vergleichsschluessel eines Portnamens. Windows kennt ``com3`` und
    ``COM3`` als denselben Anschluss; unter POSIX kann ein Port ueber einen
    Symlink (``/dev/serial/by-id/…``) angegeben sein."""
    p = (port or "").strip()
    if os.name == "nt":
        return p.upper()
    try:
        return os.path.realpath(p) if p.startswith("/") else p
    except Exception:
        return p


# OUT-66: Welche EnttecPro-Instanz IN DIESEM PROZESS welchen Port offen hat,
# und welche Seriennummer zu welcher Instanz gehoert. Ein Reconnect nimmt nie
# einen Port, den eine andere Instanz offen hat, und nie einen Dongle, dessen
# Seriennummer einer anderen Instanz gehoert. Zwischen den Worker-Prozessen
# des Proxys sorgt dafuer das Betriebssystem (Windows oeffnet exklusiv, unter
# POSIX ``exclusive=True``).
_REG_LOCK = threading.Lock()
_OFFEN: dict[str, int] = {}          # port_key -> id(instanz)
_SN_BESITZER: dict[str, int] = {}    # seriennummer -> id(instanz)


def _registry_freigeben(owner: int, auch_seriennr: bool = True):
    with _REG_LOCK:
        for k in [k for k, v in _OFFEN.items() if v == owner]:
            del _OFFEN[k]
        if auch_seriennr:
            for k in [k for k, v in _SN_BESITZER.items() if v == owner]:
                del _SN_BESITZER[k]


def _ist_sperr_fehler(exc: BaseException) -> bool:
    """True, wenn das Oeffnen nur an der Exklusiv-Sperre (``flock``) scheiterte
    — der Port also da ist, aber jemand anderes ihn exklusiv haelt."""
    if getattr(exc, "errno", None) in (errno.EAGAIN, errno.EWOULDBLOCK):
        return True
    return "exclusively lock" in str(exc)


def _seriennummer_von(device: str) -> str | None:
    """Seriennummer des Enttec an ``device`` laut ``comports()`` (sonst None)."""
    key = _port_key(device)
    try:
        for dev, sn in enttec_kandidaten():
            if _port_key(dev) == key:
                return sn
    except Exception:
        pass
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
    ``universes.json`` (damals noch unter ``data/``) fuer das Enttec-Universe weiter ``"COM_FAKE"``. Auf
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
        # OUT-66: der KONFIGURIERTE Port. ``port`` folgt dem Dongle, wenn er nach
        # einem Replug an neuer Nummer haengt (SERIAL-02); ``konfig_port`` bleibt
        # — er ist der Schluessel der NOT-AUS-Sperre je Ausgabeweg (OUT-64,
        # ``OutputManager._weg_enttec``), die sonst nach dem Wechsel nicht mehr
        # griffe.
        self.konfig_port = port
        # OUT-66: Seriennummer des Dongles, sobald einmal offen (falls das System
        # eine meldet). Daran erkennt der Reconnect SEINEN Dongle wieder.
        self._seriennr: str | None = None
        # Ohne close() verschwundene Instanzen geben ihre Eintraege trotzdem frei
        # (sonst sperrte eine tote Instanz den Port/Dongle fuer immer).
        import weakref
        weakref.finalize(self, _registry_freigeben, id(self))
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
        self._ser = self._oeffne(port, exklusiv_pflicht=False)
        self._geoeffnet(port)

    @staticmethod
    def _oeffne(port: str, exklusiv_pflicht: bool):
        """Port oeffnen; unter POSIX mit ``exclusive=True`` (OUT-66).

        Windows oeffnet serielle Ports ohnehin exklusiv. Unter Linux/macOS
        darf sonst jeder Prozess denselben Port mitbenutzen — ein Reconnect
        landete dann auf dem Dongle eines anderen Universums, obwohl der
        belegt ist. Haelt jemand den EIGENEN, konfigurierten Port exklusiv
        (``exklusiv_pflicht=False``), wird nur gewarnt und ohne Sperre
        geoeffnet — wie bei OUT-54: ein Ausgang, der sich wegen einer
        Vermutung abschaltet, ist im Live-Betrieb schlimmer. Ein FREMDER
        Port beim Reconnect (``exklusiv_pflicht=True``) wird so nie genommen."""
        kw = dict(timeout=1, write_timeout=0.5)
        if os.name == "posix":
            try:
                return serial.Serial(port, ENTTEC_BAUD, exclusive=True, **kw)
            except (serial.SerialException, OSError) as e:
                if exklusiv_pflicht or not _ist_sperr_fehler(e):
                    raise
                import sys
                print(f"[EnttecPro] {port} wird schon exklusiv gehalten — "
                      f"oeffne ihn trotzdem (geteilte Leitung).", file=sys.stderr)
        return serial.Serial(port, ENTTEC_BAUD, **kw)

    def _geoeffnet(self, port: str):
        """OUT-66: Port als von dieser Instanz offen eintragen, Seriennummer
        merken (nur wenn noch keine bekannt ist — sie aendert sich nie)."""
        with _REG_LOCK:
            _OFFEN[_port_key(port)] = id(self)
        if not self._seriennr:
            sn = _seriennummer_von(port)
            if sn:
                with _REG_LOCK:
                    if _SN_BESITZER.get(sn, id(self)) == id(self):
                        _SN_BESITZER[sn] = id(self)
                        self._seriennr = sn

    def _port_freigeben(self, auch_seriennr: bool = False):
        _registry_freigeben(id(self), auch_seriennr)

    def _fremd(self, device: str, sn: str | None = None) -> bool:
        """OUT-66: True, wenn ``device`` (bzw. der Dongle mit ``sn``) einer
        ANDEREN Instanz dieses Prozesses gehoert."""
        with _REG_LOCK:
            besitzer = _OFFEN.get(_port_key(device))
            if besitzer is not None and besitzer != id(self):
                return True
            if sn:
                b = _SN_BESITZER.get(sn)
                if b is not None and b != id(self):
                    return True
        return False

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
        self._port_freigeben()               # OUT-66: Port ist zu

    def _reconnect_ziel(self) -> str | None:
        """OUT-66: Wohin der Reconnect oeffnen darf — NUR zum eigenen Dongle.

        Vorher nahm er den ERSTEN per VID/PID gefundenen Enttec. Bei zwei
        Dongles war das oft der des anderen Universums (unter Linux auch, wenn
        der belegt war): zwei Universen schrieben auf einen Dongle, und die
        NOT-AUS-Sperre je Ausgabeweg (OUT-64) griff nicht, weil der Ausgang
        weiter seinen konfigurierten Port meldete.

        Reihenfolge:
        1. Seriennummer bekannt -> der Enttec mit DIESER Nummer, egal an
           welchem Port (SERIAL-02: neue COM-Nummer nach Replug).
        2. Keine bekannt -> der eigene Portname, wenn dort ein Enttec haengt;
           sonst ein anderer Port nur, wenn genau EIN Enttec sichtbar ist
           (dann ist es eindeutig der eigene — SERIAL-02).
        3. Sonst die alte Nummer (Geraet evtl. noch nicht gelistet) — ausser
           dort haengt erkennbar ein fremder Enttec.
        Ports und Seriennummern anderer Instanzen dieses Prozesses scheiden
        immer aus. ``None`` = diesen Versuch auslassen."""
        try:
            kand = enttec_kandidaten()
        except Exception:
            kand = []
        eigen = {_port_key(self.port), _port_key(self.konfig_port)}
        sn = self._seriennr
        frei = [(d, s) for d, s in kand if not self._fremd(d, s)]
        if sn:
            gleiche = [d for d, s in frei if s == sn]
            if gleiche:
                for d in gleiche:
                    if _port_key(d) in eigen:
                        return d
                return gleiche[0]
            # Das System meldet gerade keine Seriennummer: nur wenn genau ein
            # Enttec sichtbar ist und der keine Nummer zeigt.
            if len(kand) == 1 and frei and not frei[0][1]:
                return frei[0][0]
        else:
            for d, _s in frei:
                if _port_key(d) in eigen:
                    return d
            if len(kand) == 1 and frei:
                return frei[0][0]
        # Fallback: die alte Nummer — aber nie, wenn dort ein ANDERER Enttec
        # (fremde Seriennummer) haengt oder eine andere Instanz sie offen hat.
        for d, s in kand:
            if _port_key(d) == _port_key(self.port):
                if (sn and s and s != sn) or self._fremd(d, s):
                    return None
        if self._fremd(self.port):
            return None
        return self.port

    def _try_reconnect(self):
        """Gedrosselt (``_reconnect_every_s``) den Port neu oeffnen. Gelingt es, ist
        das USB wieder da -> Ausgabe reaktivieren. Schlaegt es fehl, bleibt der Port
        tot und der naechste Versuch kommt nach der Drossel-Zeit.

        SERIAL-02: Nach einem USB-Replug haengt der Enttec oft an einer NEUEN
        COM-Nummer -> ein Reconnect nur auf die alte ``self.port`` heilte NIE. Darum
        zuerst per VID/PID neu auffinden; nur wenn das nichts findet, Fallback
        auf die urspruengliche Nummer (mit Warnung).

        OUT-66: aber nur DENSELBEN Dongle — siehe :meth:`_reconnect_ziel`."""
        now = self._now()
        if (now - self._last_reconnect) < self._reconnect_every_s:
            return
        self._last_reconnect = now
        target = self._reconnect_ziel()
        if target is None:
            print(f"[EnttecPro] Reconnect {self.port}: eigener Enttec nicht "
                  f"sicher wiederzufinden — fremde Dongles werden nicht "
                  f"genommen, naechster Versuch spaeter.")
            return
        if _port_key(target) != _port_key(self.port):
            print(f"[EnttecPro] Reconnect: Enttec jetzt auf {target} "
                  f"(war {self.port}) — derselbe Dongle"
                  + (f" (Seriennummer {self._seriennr})." if self._seriennr
                     else " (einziger sichtbarer Enttec)."))
        eigen = _port_key(target) in {_port_key(self.port),
                                      _port_key(self.konfig_port)}
        try:
            self._ser = self._oeffne(target, exklusiv_pflicht=not eigen)
        except (serial.SerialException, OSError, ValueError) as e:
            # STAB-30: der Grund des gescheiterten Wiederverbindens (gedrosselt).
            from src.core.diagnose_log import melde_still
            melde_still("dmx.enttec.reconnect", e, text=f"Port {target}")
            return
        self.port = target
        self._geoeffnet(target)              # OUT-66
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

    def ausschreiben(self, frist_s: float = 0.3) -> bool:
        """OUT-71: warten, bis der Ausgabepuffer des Treibers leer ist — das
        zuletzt geschriebene Bild also wirklich auf der Leitung war. Noetig vor
        ``close()``, das den Puffer verwirft. Hoechstens ``frist_s``; liefert,
        ob der Puffer leer wurde. Bewusst NICHT ``Serial.flush()``: das wartet
        unter Windows ohne Grenze, wenn das Geraet nichts mehr abnimmt."""
        if self._disabled or not self._ser.is_open:
            return False
        ende = time.monotonic() + max(0.0, float(frist_s))
        while True:
            try:
                if int(self._ser.out_waiting) <= 0:
                    return True
            except Exception:
                return False        # Port weg / Treiber kennt die Abfrage nicht
            if time.monotonic() >= ende:
                return False
            time.sleep(0.005)

    def close(self):
        """Schliesst den Port. Vorher den Output-Puffer abbrechen/leeren — sonst kann
        CloseHandle() unter Windows mit einem noch ausstehenden WriteFile kollidieren
        (Access Violation beim Beenden, crash.log 22.06.). Idempotent + fehlertolerant."""
        self._port_freigeben(auch_seriennr=True)     # OUT-66
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
