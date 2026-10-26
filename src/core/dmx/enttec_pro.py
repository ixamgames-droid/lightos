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


def pro_kandidaten() -> list[tuple[str, bool]]:
    """Serielle Ports, die ein Pro-kompatibles Interface sein KOENNEN:
    ``[(port, eindeutig)]``, eindeutige zuerst.

    OUT-70: ``0403:6001`` ist die Kennung des FTDI-Chips, nicht die eines
    Enttec Pro — dieselbe tragen „Open DMX“-Kabel, der Eurolite Pro Mk2 und
    beliebige FT232-Adapter. ``eindeutig`` ist nur, wer sich mit seinem
    Produkttext als Pro-Format-Geraet ausweist („DMX USB PRO“, „ULTRADMX“,
    „DMXIS“). Geraete, die sich als etwas ANDERES ausweisen, fehlen ganz.
    Gelesen wird nur die Portliste; kein Port wird geoeffnet.
    """
    from src.core.dmx.interfaces import ist_pro_kandidat
    sicher, unklar = [], []
    for port in serial.tools.list_ports.comports():
        if port.vid != ENTTEC_VID or port.pid != ENTTEC_PID:
            continue
        try:
            art = ist_pro_kandidat(port.vid, port.pid,
                                   str(getattr(port, "manufacturer", "") or ""),
                                   str(getattr(port, "product", "") or ""))
        except Exception:                                # noqa: BLE001
            art = 1
        if art == 2:
            sicher.append((port.device, True))
        elif art == 1:
            unklar.append((port.device, False))
    return sicher + unklar


def find_enttec_port() -> str | None:
    """Sucht den Port eines Pro-kompatiblen Interfaces.

    OUT-70: haelt nicht mehr jedes ``0403:6001`` fuer einen Enttec Pro. Ein
    Geraet, das sich als Pro ausweist, gewinnt vor einem FTDI-Adapter mit
    unklarem Typ; ein Geraet, das sich als etwas anderes ausweist, wird nie
    genommen. **Steckt nur ein FTDI-Adapter mit unklarem Typ, wird er wie
    bisher geliefert** — viele Pro-kompatible Adapter melden sich schlicht als
    „FT232R USB UART“, und eine eingerichtete Ausgabe darf nach einem Update
    nicht ausfallen. Ob der Fund sicher ist, sagt :func:`pro_kandidaten`.
    """
    kandidaten = pro_kandidaten()
    return kandidaten[0][0] if kandidaten else None


def port_art(port: str) -> str:
    """Was ist an ``port`` angeschlossen? ``"pro"`` (weist sich als Pro aus),
    ``"unklar"`` (FTDI, Typ nicht ablesbar) oder ``""`` (keine Auskunft)."""
    try:
        for p, eindeutig in pro_kandidaten():
            if p == port:
                return "pro" if eindeutig else "unklar"
    except Exception:                                    # noqa: BLE001
        pass
    return ""


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


# OUT-66 (Runde 3): Eintraege der Fremdmenge mit diesem Praefix sind keine
# Seriennummern, sondern die Kennung einer ANDEREN konfigurierten Ausgabe, die
# ihren Dongle noch nicht kennt (z. B. ``?U2 (COM4)``). Solange es so eine gibt,
# wird kein Ersatz-Dongle uebernommen: er koennte genau deren Dongle sein.
OHNE_NUMMER = "?"
# Anfang des Hinweises „Ersatz NICHT uebernommen“ (voruebergehend; ein neu
# gestarteter Worker uebernimmt ihn nicht als bleibenden Hinweis).
SPERR_HINWEIS = "Nicht übernommen:"


def ist_sperr_hinweis(text) -> bool:
    return str(text or "").startswith(SPERR_HINWEIS)


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
        return ("Fuer dieses Universum ist kein Enttec-Port konfiguriert."
                + (f" Vorschlag: {gefunden} (per VID/PID gefunden)."
                   if gefunden else " Es ist auch keiner per VID/PID sichtbar."))

    grund = (f"Der konfigurierte Port {want!r} ist ein Portname von einer anderen "
             f"Plattform — die Konfiguration stammt vermutlich von einem anderen "
             f"Rechner."
             if port_is_foreign(want) else
             f"Der konfigurierte Port {want!r} existiert auf diesem System nicht.")
    if gefunden:
        return (f"{grund} Es geht kein DMX ueber diesen Adapter raus. "
                f"Vorschlag: im Reiter „Universen“ (Ausgabe → Konfigurieren…) auf {gefunden} umstellen "
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

    def __init__(self, port: str, seriennr: str | None = None, melde=None,
                 fremde=None, hinweis: str = "", frueher=()):
        """``seriennr`` (OUT-66): die Seriennummer, die diese Ausgabe schon
        einmal gelernt hat — der Prozess-Proxy reicht sie einem NEU gestarteten
        Worker mit, damit der gezielt SEINEN Dongle sucht. ``melde(port, sn,
        hinweis)`` wird nach jedem erfolgreichen Oeffnen gerufen (Rueckmeldung
        an den Proxy: aktueller Port, gelernte Seriennummer, Hinweis bei
        uebernommenem Ersatz-Dongle).

        ``fremde`` (OUT-66, Review 2): die Seriennummern, die ANDERE
        konfigurierte Enttec-Ausgaben gelernt haben — eine Menge oder eine
        Funktion, die sie liefert (Worker: liest das gemeinsame Feld des
        Proxys). Der ``OutputManager`` haelt sie aktuell
        (:meth:`setze_fremde_seriennr`). Einen Dongle mit einer dieser Nummern
        nimmt die Ausgabe nie; einen anderen Dongle am EIGENEN konfigurierten
        Port (Ersatzgeraet) uebernimmt sie und lernt seine Nummer neu.

        Runde 3: Eintraege mit Praefix :data:`OHNE_NUMMER` in ``fremde`` sind
        ANDERE Ausgaben, die ihren Dongle noch nicht kennen — solange es eine
        gibt, wird kein Ersatz uebernommen (Hinweis statt Licht), sonst
        koennten zwei Universen still tauschen. ``hinweis``/``frueher``: vom
        Proxy gehaltener bleibender Hinweis und die frueher eigenen Nummern
        (ein neu gestarteter Worker vergisst sie so nicht)."""
        self.port = port
        self._melde = melde
        self._fremde_quelle = fremde
        # OUT-66: sichtbarer Hinweis (Ausgabe-Diagnose), wenn ein anderer
        # Dongle am eigenen Port uebernommen wurde; leer = nichts zu melden.
        self._hinweis = "" if ist_sperr_hinweis(hinweis) else str(hinweis or "")
        # Runde 3: voruebergehender Hinweis „Ersatz nicht uebernommen“ (leer,
        # sobald wieder ein Dongle offen ist).
        self._sperr_hinweis = ""
        # Runde 3: Seriennummern, die diese Ausgabe VOR einer Ersatz-Uebernahme
        # hatte. Der OutputManager reicht sie als „frueher eigen“ in die
        # Fremdmenge der ANDEREN Ausgaben (zweite Sicherung gegen Tausch).
        self._frueher: set[str] = {str(x).strip() for x in (frueher or ())
                                   if x and str(x).strip()}
        # OUT-66: der KONFIGURIERTE Port. ``port`` folgt dem Dongle, wenn er nach
        # einem Replug an neuer Nummer haengt (SERIAL-02); ``konfig_port`` bleibt
        # — er ist der Schluessel der NOT-AUS-Sperre je Ausgabeweg (OUT-64,
        # ``OutputManager._weg_enttec``), die sonst nach dem Wechsel nicht mehr
        # griffe.
        self.konfig_port = port
        # OUT-66: Seriennummer des Dongles, sobald einmal offen (falls das System
        # eine meldet). Daran erkennt der Reconnect SEINEN Dongle wieder.
        self._seriennr: str | None = (str(seriennr).strip() or None
                                      if seriennr else None)
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
        ziel = self._start_ziel()
        eigen = _port_key(ziel) == _port_key(port)
        self._ser, exklusiv = self._oeffne(ziel, exklusiv_pflicht=not eigen)
        self.port = ziel
        # OUT-66 (Review): Bekam diese Instanz den Port NICHT exklusiv, haelt ihn
        # ein anderer (z. B. der Worker des anderen Universums nach vertauschtem
        # Wiedereinstecken). Dessen Seriennummer darf sie sich nicht als eigene
        # merken — sonst folgte auch jeder spaetere Reconnect dem fremden Dongle.
        if not self._geoeffnet(ziel, lernen=exklusiv):
            # Runde 3: erst jetzt als Ersatz erkannt, aber gesperrt -> zu.
            self._schliessen_still()
            raise serial.SerialException(f"{ziel}: {self._sperr_hinweis}")

    def _start_ziel(self) -> str:
        """OUT-66: Wohin das ERSTE Oeffnen geht. Ohne bekannte Seriennummer der
        konfigurierte Port (wie bisher). Mit bekannter (Worker-Neustart) der
        Dongle mit DIESER Nummer — bevorzugt am eigenen Port, sonst an seiner
        neuen Nummer (SERIAL-02). Haengt am eigenen Port erkennbar ein ANDERER
        Dongle und der eigene ist nicht zu sehen -> SerialException (der Worker
        versucht es gedrosselt erneut), statt fremd zu schreiben."""
        port, sn = self.port, self._seriennr
        try:
            kand = enttec_kandidaten()
        except Exception:
            kand = []
        if sn:
            gleiche = [d for d, s in kand if s == sn and not self._verboten(d, s)]
            for d in gleiche:
                if _port_key(d) == _port_key(port):
                    return d
            if gleiche:
                return gleiche[0]
        # Review 2: am eigenen Port haengt ein Dongle mit ANDERER Nummer (oder
        # es ist noch keine bekannt). Kennt eine andere Ausgabe diese Nummer,
        # ist es deren Dongle -> nie nehmen. Sonst ist es ein Ersatzgeraet und
        # wird uebernommen (:meth:`_geoeffnet` lernt die Nummer neu).
        for d, s in kand:
            if _port_key(d) == _port_key(port) and s and self._verboten(d, s):
                # OUT-80: sichtbar machen (Ausgabe-Diagnose), nicht nur im
                # Worker werfen — typisch nach vertauschtem Einstecken, wenn
                # der eigene Dongle fehlt.
                self._sperr_hinweis = (
                    f"{SPERR_HINWEIS} Enttec an {d} (Seriennr. {s}) gehört "
                    f"einer anderen Ausgabe"
                    + (f"; eigener Dongle (Seriennr. {sn}) nicht gefunden"
                       if sn else ""))
                self._melden(None)
                raise serial.SerialException(
                    f"{port}: dort haengt der Enttec einer anderen Ausgabe "
                    f"(Seriennr. {s}) — wird nicht genommen (OUT-66)")
            # Runde 3: Ersatz nur, wenn keine andere Ausgabe ohne gelernte
            # Nummer existiert — sonst koennte er genau deren Dongle sein.
            if (sn and _port_key(d) == _port_key(port) and s and s != sn
                    and self._ersatz_sperren(d, s)):
                raise serial.SerialException(f"{port}: {self._sperr_hinweis}")
        return port

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
        Port beim Reconnect (``exklusiv_pflicht=True``) wird so nie genommen.

        Gibt ``(ser, exklusiv)`` zurueck; ``exklusiv`` ist False nur im
        geteilten Notfall-Pfad (ein anderer haelt den Port)."""
        kw = dict(timeout=1, write_timeout=0.5)
        if os.name == "posix":
            try:
                return serial.Serial(port, ENTTEC_BAUD, exclusive=True, **kw), True
            except (serial.SerialException, OSError) as e:
                if exklusiv_pflicht or not _ist_sperr_fehler(e):
                    raise
                import sys
                print(f"[EnttecPro] {port} wird schon exklusiv gehalten — "
                      f"oeffne ihn trotzdem (geteilte Leitung).", file=sys.stderr)
            return serial.Serial(port, ENTTEC_BAUD, **kw), False
        return serial.Serial(port, ENTTEC_BAUD, **kw), True

    def _schliessen_still(self):
        try:
            self._ser.close()
        except Exception:
            pass
        self._port_freigeben()

    def _ersatz_sperren(self, device: str, ist: str) -> bool:
        """OUT-66 (Runde 3): True, wenn ein Ersatz-Dongle ``ist`` an ``device``
        NICHT uebernommen werden darf, weil eine andere konfigurierte Ausgabe
        ihren Dongle noch nicht kennt (er koennte deren sein). Setzt dann den
        Hinweis und meldet ihn (Proxy: gemeinsames Feld)."""
        andere = self._ohne_nummer()
        if not andere:
            return False
        wer = (f"Ausgabe {andere[0]} ihren Dongle noch nicht kennt"
               if len(andere) == 1 else
               f"die Ausgaben {', '.join(andere)} ihre Dongles noch nicht kennen")
        text = (f"{SPERR_HINWEIS} anderer Enttec an {device} (Seriennr. {ist}), "
                f"weil {wer}")
        if text != self._sperr_hinweis:
            import sys
            print(f"[EnttecPro] {text} (OUT-66).", file=sys.stderr)
        self._sperr_hinweis = text
        self._melden(None)
        return True

    def _melden(self, port):
        if self._melde is None:
            return
        try:
            self._melde(port, self._seriennr, self.hinweis(),
                        tuple(sorted(self._frueher)))
        except Exception:
            pass

    def _geoeffnet(self, port: str, lernen: bool = True) -> bool:
        """OUT-66: Port als von dieser Instanz offen eintragen, Seriennummer
        merken (nur, wenn der Port exklusiv offen ist: ``lernen``).

        Eine schon bekannte Nummer wird nur in EINEM Fall ersetzt (Review 2):
        am KONFIGURIERTEN Port steckt jetzt ein anderer Dongle, dessen Nummer
        keine andere Ausgabe kennt — ein Ersatzgeraet. Dann lernt die Ausgabe
        dessen Nummer und meldet die Uebernahme sichtbar (:meth:`hinweis`).

        Runde 3: gibt False zurueck, wenn es ein Ersatz waere, der gesperrt
        ist (:meth:`_ersatz_sperren`) — der Aufrufer schliesst dann wieder."""
        with _REG_LOCK:
            _OFFEN[_port_key(port)] = id(self)
        if self._seriennr and lernen \
                and _port_key(port) == _port_key(self.konfig_port):
            ist = _seriennummer_von(port)
            if ist and ist != self._seriennr and not self._verboten(port, ist):
                if self._ersatz_sperren(port, ist):
                    return False
                alt, self._seriennr = self._seriennr, None
                self._frueher.add(alt)            # Runde 3: „frueher eigen“
                _registry_freigeben(id(self), auch_seriennr=True)
                with _REG_LOCK:
                    _OFFEN[_port_key(port)] = id(self)
                self._hinweis = (f"Anderer Enttec an {port} übernommen: "
                                 f"Seriennr. {ist} statt Seriennr. {alt}")
                import sys
                print(f"[EnttecPro] {self._hinweis} (OUT-66).", file=sys.stderr)
        if self._seriennr:
            with _REG_LOCK:
                if _SN_BESITZER.get(self._seriennr, id(self)) == id(self):
                    _SN_BESITZER[self._seriennr] = id(self)
        elif lernen:
            sn = _seriennummer_von(port)
            if sn:
                with _REG_LOCK:
                    if _SN_BESITZER.get(sn, id(self)) == id(self):
                        _SN_BESITZER[sn] = id(self)
                        self._seriennr = sn
        self._sperr_hinweis = ""                  # Runde 3: wieder ein Dongle offen
        self._melden(self.port)
        return True

    def _port_freigeben(self, auch_seriennr: bool = False):
        _registry_freigeben(id(self), auch_seriennr)

    # ── OUT-66 (Review 2): fremde Seriennummern, Auskunft fuer den Manager ────

    def setze_fremde_seriennr(self, menge):
        """Vom ``OutputManager``: die Seriennummern der ANDEREN konfigurierten
        Enttec-Ausgaben (ersetzt eine beim Anlegen mitgegebene Quelle)."""
        self._fremde_quelle = frozenset(str(s) for s in (menge or ()) if s)

    def _fremde_eintraege(self) -> frozenset:
        q = self._fremde_quelle
        try:
            werte = q() if callable(q) else q
            return frozenset(str(s) for s in (werte or ()) if s)
        except Exception:
            return frozenset()

    def _fremde_sn(self) -> frozenset:
        return frozenset(s for s in self._fremde_eintraege()
                         if not s.startswith(OHNE_NUMMER))

    def _ohne_nummer(self) -> list[str]:
        """Runde 3: Kennungen der ANDEREN Ausgaben ohne gelernte Nummer."""
        return sorted(s[len(OHNE_NUMMER):].strip()
                      for s in self._fremde_eintraege()
                      if s.startswith(OHNE_NUMMER)
                      and s[len(OHNE_NUMMER):].strip())

    @property
    def frueher_seriennr(self) -> frozenset:
        """Runde 3: Nummern, die diese Ausgabe vor einer Ersatz-Uebernahme
        hatte (bleiben fuer die anderen fremd)."""
        return frozenset(self._frueher)

    def _verboten(self, device: str, sn: str | None = None) -> bool:
        """True, wenn ``device``/``sn`` einer anderen Instanz dieses Prozesses
        gehoert ODER eine andere konfigurierte Ausgabe die Nummer kennt."""
        if self._fremd(device, sn):
            return True
        return bool(sn) and sn in self._fremde_sn()

    @property
    def seriennr(self) -> str | None:
        """Die gelernte USB-Seriennummer (sonst None)."""
        return self._seriennr

    @property
    def port_aktuell(self) -> str:
        """Der Port, an dem GERADE gesendet wird — nur solange der Port offen
        ist; sonst der konfigurierte (Review 2: ein toter Ausgang belegt keine
        fremde Nummer, ``close_enttec_on_port`` verdraengt ihn dort nicht)."""
        try:
            offen = (not self._disabled) and bool(self._ser.is_open)
        except Exception:
            offen = False
        return self.port if offen else self.konfig_port

    @property
    def port_zuletzt(self) -> str:
        """Der zuletzt geoeffnete Port, auch nach einem Ausfall (NOT-AUS-Weg:
        lieber eine Nummer zu viel gesperrt als eine zu wenig)."""
        return self.port

    def hinweis(self) -> str:
        """OUT-66: Hinweis fuer die Ausgabe-Diagnose (leer = nichts). Ein
        gerade gesperrter Ersatz (Runde 3) steht vorn."""
        return "; ".join(t for t in (self._sperr_hinweis, self._hinweis) if t)

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
        frei = [(d, s) for d, s in kand if not self._verboten(d, s)]
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
            # Review 2: Ersatzgeraet am KONFIGURIERTEN Port — uebernehmen, wenn
            # keine andere Ausgabe seine Nummer kennt (sonst nie).
            # Runde 3: und nur, wenn keine andere Ausgabe ohne gelernte Nummer
            # existiert (der Dongle koennte deren sein).
            for d, s in kand:
                if _port_key(d) == _port_key(self.konfig_port) and s and s != sn:
                    if self._verboten(d, s) or self._ersatz_sperren(d, s):
                        return None
                    return d
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
                if (sn and s and s != sn) or self._verboten(d, s):
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
            self._ser, exklusiv = self._oeffne(target, exklusiv_pflicht=not eigen)
        except (serial.SerialException, OSError, ValueError) as e:
            # STAB-30: der Grund des gescheiterten Wiederverbindens (gedrosselt).
            from src.core.diagnose_log import melde_still
            melde_still("dmx.enttec.reconnect", e, text=f"Port {target}")
            return
        self.port = target
        if not self._geoeffnet(target, lernen=exklusiv):   # OUT-66
            self._schliessen_still()                # Runde 3: gesperrter Ersatz
            return
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
