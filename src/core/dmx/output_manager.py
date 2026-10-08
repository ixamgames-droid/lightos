"""Output Manager — koordiniert alle DMX-Ausgabegeräte bei 44 Hz."""
from contextlib import contextmanager
import os
import threading
import time
from .universe import Universe
from .enttec_pro import EnttecPro
from .artnet import ArtNetSender
from .sacn import SACNSender

TARGET_HZ = 44
FRAME_INTERVAL = 1.0 / TARGET_HZ


def _make_enttec_device(port: str):
    """Erzeugt das Enttec-Ausgabegeraet.

    STAB-08: Standardmaessig ein PROZESS-ISOLIERTER Proxy — eine native Access
    Violation im USB-/FTDI-Treiber (Kabel mitten im WriteFile abgezogen) killt dann
    nur den Worker-Prozess, nicht LightOS; der Parent respawnt ihn. Mit
    ``LIGHTOS_SERIAL_INPROC=1`` (Tests/Debug/Fallback) wird stattdessen der direkte
    In-Prozess-:class:`EnttecPro` benutzt. Schlaegt der Proxy-Start fehl, faellt es
    ebenfalls auf In-Prozess zurueck — die Isolation darf die Ausgabe nie ganz
    verhindern."""
    # OUT-54: fremde Halter des Ports melden, BEVOR wir selbst oeffnen. Nur
    # warnen, nicht blockieren — ein Ausgang, der sich wegen einer Vermutung
    # abschaltet, ist im Live-Betrieb schlimmer als einer, der sich die Leitung
    # teilt. Die Meldung nennt PID und Kommandozeile; genau die fehlten am
    # 26.08.2026, als fuenf Sender gleichzeitig auf /dev/ttyUSB0 schrieben.
    try:
        from .port_check import warne_wenn_belegt
        warne_wenn_belegt(port)
    except Exception:                                    # noqa: BLE001
        pass                                             # Diagnose darf nie stoeren
    if os.environ.get("LIGHTOS_SERIAL_INPROC"):
        return EnttecPro(port)
    try:
        from .serial_process import EnttecProcessProxy
        return EnttecProcessProxy(port)
    except Exception as e:
        import sys
        print(f"[OutputManager] Serial-Prozess-Isolation nicht verfuegbar ({e}) "
              f"-> In-Prozess-Fallback.", file=sys.stderr)
        return EnttecPro(port)


# ── OUT-51: Sendefehler zaehlen statt schlucken ──────────────────────────────
#
# Vorher lagen um jeden ``send_dmx()`` drei blanke ``except Exception: pass``.
# Ein Geraet konnte mitten in der Show ausfallen, ohne dass IRGENDWO etwas
# erschien — kein Zaehler, kein Log, kein Signal an die UI.
#
# ★ Warum nicht einfach loggen? Weil dieser Pfad 44 Mal pro Sekunde laeuft.
# Ein ``print`` je Fehlversuch waere bei abgezogenem Adapter eine Log-Flut, die
# genau das begraebt, was sie zeigen soll. Deshalb: zaehlen (billig, im
# Output-Thread), und die MELDUNG an eine Schwelle plus eine Drossel haengen.
# Was die UI zeigt, holt sie sich gelesen — der Output-Thread ruft nie in die UI.

# So viele Fehler IN FOLGE gelten als "anhaltender Ausfall" (bei 44 Hz gut eine
# halbe Sekunde). Bewusst derselbe Wert wie ``EnttecPro.FAIL_LIMIT``: ein
# einzelner Hickup — ein verpasstes UDP-Paket, ein Frame Timeout — ist kein
# Ausfall und darf nichts melden.
SENDE_FEHLER_SCHWELLE = 20
# Wiederholte Meldung desselben, weiter bestehenden Ausfalls (Sekunden).
SENDE_MELDE_INTERVALL_S = 30.0


class _Sendezaehler:
    """Fehlerzustand EINES Ausgabewegs (z. B. Enttec auf Universum 3).

    ``fehler`` zaehlt AUFEINANDERFOLGENDE Fehlversuche und wird bei jedem
    erfolgreichen Frame auf 0 gesetzt — nur ein anhaltender Abriss ueberschreitet
    damit die Schwelle. ``gesamt`` zaehlt weiter und bleibt stehen: daran ist
    hinterher zu sehen, dass es geruckelt hat, auch wenn gerade alles laeuft.
    """
    __slots__ = ("fehler", "gesamt", "text", "seit", "gemeldet_um")

    def __init__(self):
        self.fehler = 0            # Fehler in Folge (0 = laeuft)
        self.gesamt = 0            # alle Fehler, seit der Manager laeuft
        self.text = ""             # letzte Fehlermeldung (fuer Tooltip/Log)
        self.seit = 0.0            # monotone Zeit des ersten Fehlers der Serie
        self.gemeldet_um = 0.0     # wann zuletzt gemeldet (Drossel)

    @property
    def anhaltend(self) -> bool:
        return self.fehler >= SENDE_FEHLER_SCHWELLE


# Zustaende eines Ausgabegeraets. VERBINDET und UNBEKANNT sind BEIDE "nicht
# gewiss", muessen aber getrennt bleiben: "verbindet gerade" ist ein bekannter
# Uebergang und darf gelb angezeigt werden, "keine Auskunft moeglich" ist gar
# kein Befund und darf deshalb WEDER Alarm ausloesen NOCH Erfolg behaupten.
ZUSTAND_SENDET = "sendet"
ZUSTAND_TOT = "tot"
ZUSTAND_VERBINDET = "verbindet"
ZUSTAND_UNBEKANNT = "unbekannt"


def geraet_zustand(dev) -> str:
    """Was macht dieses Ausgabegeraet gerade? — einer der vier ``ZUSTAND_*``.

    ★ Der Unterschied, um den es in OUT-51 geht: *registriert* ist nicht
    *verbunden*. ``EnttecProcessProxy.is_open()`` meldet nur, dass der
    Worker-PROZESS lebt — bei totem COM-Port laeuft der munter weiter und
    versucht gedrosselt neu zu oeffnen. Nur ``is_connected()`` (SERIAL-01) sagt,
    ob Frames rausgehen; es stand bis hierhin dokumentiert im Code und hatte
    **keinen einzigen Konsumenten** in der UI.

    ``ZUSTAND_UNBEKANNT`` ist Absicht und kein Bequemlichkeitswert: ein
    Art-Net-Socket KANN nicht wissen, ob am anderen Ende jemand zuhoert (UDP).
    Daraus "tot" zu machen hiesse, eine funktionierende Ausgabe als kaputt zu
    melden — und daraus "sendet" zu machen waere genau die Luege, die dieses
    Item abstellt.

    ``ZUSTAND_VERBINDET`` haelt keinen Ausfall verborgen, sondern verzoegert das
    Urteil um die Anlaufzeit: bleibt der Port zu, setzt der Worker von selbst
    ``ST_DISABLED``. Ohne diesen Zustand faerbte die Statusleiste in den ersten
    Sekunden nach jedem „Verbinden" rot.
    """
    f = getattr(dev, "status", None)
    if callable(f):
        try:
            from .serial_process import ST_CONNECTING
            if f() == ST_CONNECTING:
                return ZUSTAND_VERBINDET
        except Exception:
            pass
    for name in ("is_connected", "is_disabled", "is_open"):
        f = getattr(dev, name, None)
        if not callable(f):
            continue
        try:
            wert = bool(f())
        except Exception:
            return ZUSTAND_UNBEKANNT
        if name == "is_disabled":
            # Ein als tot markierter Port ist sicher NICHT verbunden; ein nicht
            # markierter kann trotzdem geschlossen sein -> weiter zu is_open().
            if wert:
                return ZUSTAND_TOT
            continue
        return ZUSTAND_SENDET if wert else ZUSTAND_TOT
    return ZUSTAND_UNBEKANNT


def geraet_verbunden(dev) -> bool | None:
    """Sendet dieses Geraet WIRKLICH? ``None`` = nicht gewiss (s.
    :func:`geraet_zustand`, dessen zwei ungewisse Faelle hier zusammenfallen)."""
    z = geraet_zustand(dev)
    if z == ZUSTAND_SENDET:
        return True
    if z == ZUSTAND_TOT:
        return False
    return None


def _kopf_schluessel(h):
    """Kopf-Schluessel eines Submaster-Slots: ``int`` fuer Farbkoepfe,
    ``"wN"`` fuer Weiss-Segmente (FM-41); Unbrauchbares -> ``None``."""
    if isinstance(h, str) and h.startswith("w") and h[1:].isdigit():
        return h
    try:
        return int(h)
    except (TypeError, ValueError):
        return None


class OutputManager:
    #: LAS-24: unterhalb dieses Grand-Master-Werts gelten Laser ohne Dimmer als
    #: „aus“ (Betriebsart auf den Aus-Wert). Darueber sind sie unveraendert an —
    #: eine Betriebsart laesst sich nicht stufenlos skalieren.
    GM_LASER_AUS_SCHWELLE = 0.01

    def __init__(self):
        self.universes: dict[int, Universe] = {}
        self._enttec_outputs: dict[int, EnttecPro] = {}   # universe → device
        self._artnet_outputs: dict[int, ArtNetSender] = {}  # universe → sender
        self._thread: threading.Thread | None = None
        self._running = False
        # Schuetzt den Zugriff auf die Ausgabe-Geraete (Enttec/ArtNet/sACN) gegen
        # gleichzeitiges Senden (Output-Thread) und Verbinden/Trennen (UI-Thread).
        # OHNE diesen Lock fuehrte close()/Reconnect aus dem UI-Thread, waehrend
        # der Output-Thread mitten im send_dmx() steckt, unter Windows (pyserial)
        # zum Deadlock und damit zum kompletten Einfrieren der App.
        self._io_lock = threading.RLock()
        # Wartezeit beim Stop auf das saubere Ende des Output-Threads, bevor Geraete
        # geschlossen werden (testbar ueberschreibbar).
        self._stop_join_s = 2.0
        self._blackout = False
        # BUG-FBW Slice 3: eingefrorene Frames (None = laeuft normal), s. set_freeze.
        self._freeze_frames: dict[int, bytes] | None = None
        # OUT-60 (+Folgen): Zustand der Lade-Sperre als EIN Tupel
        # ``(frames, (gm, keep, ziel, estop))`` oder None. Ein Tupel, damit der
        # Sende-Thread Frame und Masken atomar sieht — getrennte Attribute
        # konnten am Sperr-Ende auseinanderlaufen (Review A zu #927).
        self._lade: tuple | None = None
        self._lade_tiefe = 0
        # OUT-61b: Laser-Adressen unabhaengig vom Latch + ausdruecklicher Latch.
        self._laser_adressen: dict = {}
        self._laser_estop_aktiv = False
        # slot → (level 0.0–1.0, target_fids | None). target_fids None = GLOBALER
        # Submaster (wirkt auf ALLE Fixtures, bisheriges Verhalten); ein
        # frozenset[int] beschraenkt den Submaster auf genau diese Fixture-fids
        # (zuweisbarer Submaster). Jeder VC-Submaster-Fader belegt einen eigenen
        # Slot (Widget-ID), damit sich mehrere Submaster nicht ueberschreiben.
        self._submasters: dict = {}
        self._sacn_outputs: dict[int, SACNSender] = {}  # universe → sender
        # OUT-03: pro internem Universum eine optionale, explizit konfigurierte
        # EXTERNE Universe-Nummer fuer Art-Net/sACN. Fehlt ein Eintrag, gilt der
        # abwaertskompatible Default (Art-Net = num-1, sACN = num). {internal:int
        # -> external:int}
        self._out_universe: dict[int, int] = {}
        self._tick_callbacks: list = []   # callables(dt: float)
        self.grand_master: float = 1.0  # 0.0–1.0 — globale Helligkeit
        self._gm_callbacks: list = []   # callables(value: float)
        self._blackout_callbacks: list = []   # callables(enabled: bool), UI-58
        # Adressen je Universum, die der Grand-Master skalieren darf (Intensitaet/
        # Farbe — NICHT Pan/Tilt/Gobo). Wird vom AppState aus dem Patch gesetzt
        # (_rebuild_render_plan). Universen OHNE Eintrag (rein roh/ungepatcht)
        # fallen auf "alle Kanaele" zurueck, damit reine Roh-DMX-Setups weiter
        # global dimmen. {universe:int -> frozenset[addr 1..512]}
        self._gm_address_mask: dict[int, frozenset] = {}
        # LAS-24: DMX-Laser ohne Dimmer/Farbe erreicht die GM-Skalierung nicht.
        # {universe -> {addr: aus_wert}} — bei GM unter GM_LASER_AUS_SCHWELLE
        # wird jede Adresse auf ihren „aus“-Wert (Betriebsart „Laser off“)
        # gezogen. Vom AppState aus dem Patch gepflegt.
        self._gm_laser_aus_mask: dict[int, dict] = {}
        # OUT-57: Adressen je Universum, die der BLACKOUT STEHEN LAESST (Erhalten-
        # Maske) — nur Pan/Tilt/Gobo/Prisma/Optik gepatchter Lampen mit echtem
        # Dimmer (s. AppState._build_blackout_keep_mask), damit Moving Heads beim
        # Blackout nicht in die Grundstellung fahren und beim Loesen zurueck. ALLES
        # andere geht auf 0 — auch ungepatchte Roh-Adressen im selben Universum
        # (Simple Desk, Kanal-Fader, Engine-Extra): eine Liste der Licht-Kanaele
        # waere nie vollstaendig. Universen OHNE Eintrag (ungepatcht/roh) nullt der
        # Blackout KOMPLETT. {universe:int -> frozenset[addr 1..512]}
        self._blackout_keep_mask: dict[int, frozenset] = {}
        # OUT-57: zaehlt jede echte Blackout-Aenderung hoch. Ein Skript merkt sich
        # den Stand nach seinem eigenen „blackout on" und nimmt den Blackout nur
        # zurueck, solange niemand sonst ihn seitdem angefasst hat.
        self._blackout_epoch = 0
        # VCB-11: GEZIELTE Blackouts (VC-Blackout-Taste mit Ziel). slot -> {universe:
        # frozenset[addr]} der Adressen, die DIESE Taste auf 0 zieht (Licht-Kanaele
        # ihrer Ziel-Geraete, s. AppState.set_target_blackout). Jede Taste belegt
        # einen eigenen Slot, damit sich mehrere Tasten sauber ueberlagern: das
        # Loesen der einen laesst die andere dunkel. ``_ziel_blackout_union`` ist
        # die Vereinigung aller Slots je Universum; sie wird bei jeder Aenderung
        # NEU gebunden (immutable), der Output-Thread liest sie ohne Sperre.
        self._ziel_blackouts: dict = {}
        self._ziel_blackout_union: dict[int, frozenset] = {}
        # A3D-01: Adressen je Universum, die bei aktivem Laser-NOT-AUS FINAL (nach
        # Channel-Modifier + Grand-Master + Blackout) hart auf 0 gezwungen werden.
        # Leeres Dict = kein NOT-AUS aktiv. Vom AppState gepflegt (set_laser_estop /
        # _rebuild_render_plan). Noetig, weil ein auf einer Laser-Adresse liegender
        # Channel-Modifier (INVERSE -> 255, Range-Lock -> range_min) das im Renderer
        # erzwungene Dunkel sonst nach dem Modifier-Pass wieder aufhebt.
        # {universe:int -> frozenset[addr 1..512]}
        self._laser_estop_mask: dict[int, frozenset] = {}
        # ANZEIGE-Snapshot (WYSIWYG): pro Universum die zuletzt GESENDETEN Bytes
        # NACH Grand-Master/Blackout/Channel-Modifier. Output-facing Anzeigen
        # (DMX-Monitor, Output-Monitor, 3D-Visualizer) lesen diesen Snapshot statt
        # des Roh-Universe-Puffers, damit sie den echten Output zeigen — bei
        # Blackout also alles 0, bei GM<100% skaliert. NUR-LESEN fuer die Anzeige:
        # wird NIE zurueck in den Puffer/Render geschrieben (keine Feedback-Schleife).
        # Zuweisung erfolgt GIL-atomar mit immutable ``bytes`` je Universum.
        # {universe:int -> bytes(512)}. Leer, solange noch kein Frame gesendet wurde
        # -> Konsumenten fallen dann sauber auf den Rohpuffer zurueck.
        self._display_frame: dict[int, bytes] = {}
        # OUT-51: Fehlerregister je Ausgabeweg. Schluessel (weg, universum), z. B.
        # ("Enttec", 3); ("Tick", 0) und ("Modifier", u) fuer die beiden anderen
        # Stellen, an denen der Frame-Pfad bisher still schluckte. Geschrieben
        # NUR vom Output-Thread, gelesen von der UI: dict-Zuweisung und
        # int-Inkrement auf einem bestehenden Objekt sind unter dem GIL atomar,
        # ein Leser sieht also nie ein halbes Ergebnis. Kein Lock, weil dieser
        # Pfad 44 Mal pro Sekunde laeuft und ein Lock hier den Frame-Takt
        # belasten wuerde, ohne dass ein Leser mehr davon haette.
        self._sende_fehler: dict[tuple[str, int], _Sendezaehler] = {}

    # ── Grand Master ─────────────────────────────────────────────────────────

    def set_grand_master(self, val: float):
        """Setzt Grand Master 0.0–1.0."""
        self.grand_master = max(0.0, min(1.0, float(val)))
        for cb in list(self._gm_callbacks):
            try:
                cb(self.grand_master)
            except Exception:
                pass

    def subscribe_grand_master(self, cb):
        if cb not in self._gm_callbacks:
            self._gm_callbacks.append(cb)

    def unsubscribe_grand_master(self, cb):
        """Callback wieder abmelden (z. B. wenn ein VC-Grandmaster-Fader geloescht
        wird) — sonst feuert set_grand_master() weiter auf ein totes Widget."""
        try:
            self._gm_callbacks.remove(cb)
        except ValueError:
            pass

    def set_gm_address_mask(self, mask: dict[int, frozenset]):
        """Setzt je Universum die Adressen, die der Grand-Master skalieren darf
        (Intensitaet/Farbe). Pan/Tilt/Gobo etc. bleiben unberuehrt. Vom AppState
        aus dem Patch gepflegt."""
        self._gm_address_mask = mask or {}

    def set_gm_laser_aus_mask(self, mask: dict[int, dict]):
        """LAS-24: je Universum ``{adresse: aus_wert}`` der Laser ohne Dimmer-/
        Farbkanal. Bei Grand Master < ``GM_LASER_AUS_SCHWELLE`` setzt der
        Sende-Pfad diese Adressen NACH Channel-Modifier und GM-Skalierung auf
        ihren Aus-Wert (ein INVERSE-Modifier kann den Laser so nicht wieder
        einschalten). Vom AppState aus dem Patch gepflegt."""
        self._gm_laser_aus_mask = {u: dict(m) for u, m in (mask or {}).items()}

    def set_blackout_keep_mask(self, mask: dict[int, frozenset]):
        """OUT-57: Setzt je Universum die Adressen, die der Blackout STEHEN LAESST
        (Position/Gobo/Prisma/Optik gepatchter Lampen mit echtem Dimmer); alle
        anderen Adressen zieht er auf 0. Universen ohne Eintrag nullt der Blackout
        komplett. Vom AppState aus dem Patch gepflegt."""
        self._blackout_keep_mask = mask or {}

    def set_laser_estop_mask(self, mask: dict[int, frozenset], aktiv: bool | None = None):
        """A3D-01: Setzt je Universum die Laser-Adressen, die bei aktivem NOT-AUS
        FINAL (nach Channel-Modifier/Grand-Master/Blackout) auf 0 gezwungen werden.
        Leeres Dict = keine Adressen. Vom AppState gepflegt (spiegelt
        ``_laser_estop_addrs`` solange ``laser_estop_active``).

        OUT-61b: ``aktiv`` = Zustand des NOT-AUS-Latches, AUSDRUECKLICH — eine
        leere Maske heisst nicht „aus“: im Lade-Fenster ist der Plan leer, die
        Maske also leer, obwohl der Latch gerade ausgeloest wurde. ``None`` =
        wie bisher aus der Maske ableiten."""
        self._laser_estop_mask = mask or {}
        self._laser_estop_aktiv = bool(mask) if aktiv is None else bool(aktiv)

    def set_laser_adressen(self, mask: dict[int, frozenset]):
        """OUT-61b: ALLE Laser-Adressen des aktuellen Patches, unabhaengig vom
        NOT-AUS-Latch. Die Lade-Sperre haelt sie beim Ladebeginn fest und nullt
        sie, sobald der Latch WAEHREND des Ladens aktiv wird — dann ist der Plan
        (und damit die Live-Maske) leer, und ohne diese Adressen sendete der
        eingefrorene Frame die Laserwerte weiter. Vom AppState beim Plan-Rebuild
        gepflegt."""
        self._laser_adressen = mask or {}

    def lade_laser_adressen(self) -> dict:
        """OUT-63: Laser-Adressen vom Beginn einer laufenden Lade-Sperre, sonst
        ``{}``. Wird der NOT-AUS erst WAEHREND des Ladens ausgeloest (Plan nach
        dem reset-first leer), nimmt der AppState sie in die klebrige Maske auf
        — sonst faellt der Schutz mit dem Ende der Sperre weg, obwohl der Laser
        physisch weiter an diesen Adressen haengt. Liest ``_lade`` EINMAL."""
        lade = self._lade
        if lade is None:
            return {}
        return lade[1][4] or {}

    # ── Anzeige-Snapshot (WYSIWYG) ───────────────────────────────────────────

    def get_display_frame(self, universe: int) -> bytes | None:
        """Zuletzt GESENDETE Bytes (512) fuer ``universe`` NACH Grand-Master/
        Blackout/Channel-Modifier — der echte Output fuer output-facing Anzeigen
        (DMX-Monitor, Output-Monitor, 3D-Visualizer). ``None``, solange noch kein
        Frame gesendet wurde (Output-Thread aus / kein Tick) -> der Aufrufer faellt
        dann auf den Rohpuffer (``universe.get_all()``) zurueck. NUR LESEN: der
        Snapshot wird nie zurueck in den Puffer/Render geschrieben.

        ⚠️ OUT-52: Dieser Snapshot entsteht, BEVOR nachgesehen wird, ob das
        Universum ueberhaupt einen Adapter hat (``_send_all`` setzt ihn eine
        Zeile vor dem Geraete-Block). Er zeigt also, was LightOS **gerechnet**
        hat — nicht zwingend, was ein Geraet bekommen hat. Wer ihn anzeigt,
        muss :meth:`sendet_wirklich` dazu befragen; sonst entsteht genau die
        Verwechslung, die am 2026-08-05 die Fehlersuche verlaengert hat: der
        Monitor sah richtig aus, waehrend ein leeres Universum gesendet wurde.
        """
        return self._display_frame.get(universe)

    def sendet_wirklich(self, universe: int) -> bool:
        """OUT-52: Geht der Frame dieses Universums an IRGENDEIN Geraet?

        ``False`` heisst: was :meth:`get_display_frame` liefert, ist eine reine
        Rechnung — kein Adapter ist dafuer registriert. Die Frage, ob ein
        registrierter Adapter auch wirklich sendet, beantwortet
        :meth:`ausgabe_status` (OUT-51); hier geht es nur um „gibt es
        ueberhaupt einen Ausgang".
        """
        return any(universe in reg for reg in
                   (self._enttec_outputs, self._artnet_outputs,
                    self._sacn_outputs))

    # ── OUT-51: Sendefehler buchen und auslesen ──────────────────────────────

    def _buche_fehler(self, weg: str, universum: int, exc: BaseException,
                      quelle: str = ""):
        """Einen Fehlversuch buchen und bei anhaltendem Ausfall EINMAL melden.

        Laeuft im Output-Thread (44 Hz) — deshalb passiert hier im Normalfall
        nichts ausser einem dict-Lookup und zwei Inkrementen. Die Ausgabe auf
        stderr haengt an Schwelle UND Drossel: sie kommt beim Kippen des
        Zustands und danach hoechstens alle ``SENDE_MELDE_INTERVALL_S``.
        """
        z = self._sende_fehler.get((weg, universum))
        if z is None:
            z = _Sendezaehler()
            self._sende_fehler[(weg, universum)] = z
        if z.fehler == 0:
            z.seit = time.monotonic()
        z.fehler += 1
        z.gesamt += 1
        z.text = f"{type(exc).__name__}: {exc}"
        if quelle:
            z.text = f"{quelle} -> {z.text}"
        if not z.anhaltend:
            return
        jetzt = time.monotonic()
        # gemeldet_um == 0.0 -> erste Meldung dieser Serie, sofort raus.
        if z.gemeldet_um and (jetzt - z.gemeldet_um) < SENDE_MELDE_INTERVALL_S:
            return
        z.gemeldet_um = jetzt
        import sys
        print(f"[OutputManager] {weg} Universum {universum}: {z.fehler} Frames "
              f"in Folge nicht gesendet ({z.text})", file=sys.stderr)

    def _buche_erfolg(self, weg: str, universum: int):
        """Erfolgreiches Frame — Fehlerserie beenden (und eine Erholung melden).

        Die Abfrage ``if z is None or z.fehler == 0: return`` steht bewusst
        zuerst: im Normalbetrieb ist das der einzige Aufwand, den ein
        erfolgreiches Frame verursacht.
        """
        z = self._sende_fehler.get((weg, universum))
        if z is None or z.fehler == 0:
            return
        war_anhaltend = z.anhaltend
        z.fehler = 0
        z.gemeldet_um = 0.0
        if war_anhaltend:
            import sys
            print(f"[OutputManager] {weg} Universum {universum}: sendet wieder.",
                  file=sys.stderr)

    def _vergiss_fehler(self, universum: int):
        """Fehlerzaehler eines Universums verwerfen (Adapter entfernt/getauscht).

        Ohne das meldete :meth:`sende_probleme` weiter einen Ausfall fuer einen
        Adapter, den es gar nicht mehr gibt — und ein neu angelegter startete
        mit der Fehlerserie seines Vorgaengers, waere also sofort "kaputt", ohne
        je gesendet zu haben. Die Tick-Callbacks (Schluessel-Universum 0) haengen
        an keinem Adapter und bleiben deshalb ausgenommen.
        """
        for schluessel in [k for k in list(self._sende_fehler)
                           if k[1] == universum and k[0] != "Tick"]:
            self._sende_fehler.pop(schluessel, None)

    def sende_probleme(self) -> list[dict]:
        """Ausgabewege, die GERADE anhaltend scheitern (fuer UI/Status/Log).

        Liefert je Weg ``{"weg", "universum", "fehler", "gesamt", "seit_s",
        "text"}``. Leere Liste = alles, was registriert ist, sendet auch.
        Kurze Aussetzer unterhalb der Schwelle erscheinen hier NICHT — sie
        stehen nur in ``gesamt`` (s. :meth:`sende_statistik`).
        """
        jetzt = time.monotonic()
        raus = []
        for (weg, universum), z in list(self._sende_fehler.items()):
            if not z.anhaltend:
                continue
            raus.append({
                "weg": weg, "universum": universum,
                "fehler": z.fehler, "gesamt": z.gesamt,
                "seit_s": max(0.0, jetzt - z.seit), "text": z.text,
            })
        raus.sort(key=lambda d: (d["weg"], d["universum"]))
        return raus

    def sende_statistik(self) -> dict[tuple[str, int], dict]:
        """Vollstaendiges Fehlerregister — auch erholte Wege (``gesamt`` > 0,
        ``fehler`` == 0). Fuer Diagnose und Tests; die UI nimmt
        :meth:`sende_probleme`."""
        return {k: {"fehler": z.fehler, "gesamt": z.gesamt, "text": z.text}
                for k, z in list(self._sende_fehler.items())}

    def ausgabe_status(self) -> list[dict]:
        """Was gerade WIRKLICH sendet — pro Universum und Ausgabeweg.

        Je Eintrag ``{"universum", "weg", "ziel", "verbunden", "problem"}``.
        ``verbunden`` ist dreiwertig: ``True`` sendet, ``False`` sendet nicht,
        ``None`` = das Geraet kann darueber keine Auskunft geben (UDP-Ausgaenge
        ohne Fehlerserie). Wer daraus eine gruene Anzeige baut, muss ``None``
        anders behandeln als ``True`` — sonst entsteht wieder die Anzeige, die
        Erfolg meldet, weil sie nichts weiss.
        """
        # ★ BEWUSST OHNE ``_io_lock``. Diese Methode laeuft im UI-Thread im
        # Sekundentakt, und der Output-Thread haelt den Lock waehrend des
        # Sendens — ein blockierender Serial-Write (write_timeout 0,5 s) wuerde
        # die Oberflaeche also regelmaessig anhalten. Genau dieses Warten des
        # UI-Threads auf den Output-Thread ist die Falle, gegen die es den Lock
        # ueberhaupt gibt; ihn fuer eine ANZEIGE zu nehmen kehrte sie um.
        # Sicher ist das, weil hier nur GELESEN wird: ``dict(...)`` ist unter
        # dem GIL ein atomarer Schnappschuss, und ein Geraet, das inzwischen
        # geschlossen wurde, beantwortet ``is_connected()`` weiterhin
        # fehlerfrei (und `geraet_zustand` faengt ohnehin ab).
        raus = []
        gruppen = (("Enttec", dict(self._enttec_outputs)),
                   ("Art-Net", dict(self._artnet_outputs)),
                   ("sACN", dict(self._sacn_outputs)))
        paare = [(weg, u, dev) for weg, reg in gruppen
                 for u, dev in sorted(reg.items())]
        anhaltend = {(p["weg"], p["universum"]): p for p in self.sende_probleme()}
        for weg, universum, dev in paare:
            problem = anhaltend.get((weg, universum))
            verbunden = geraet_verbunden(dev)
            if problem is not None:
                # Eine laufende Fehlerserie schlaegt die Selbstauskunft des
                # Geraets: ein UDP-Socket meldet sich nie als kaputt, aber wenn
                # 20 sendto() hintereinander geworfen haben, geht nichts raus.
                verbunden = False
            raus.append({
                "universum": universum, "weg": weg,
                # Jeder Sendertyp nennt sein Ziel anders: Enttec den `port`,
                # Art-Net `target_ip`, sACN `_target_ip` (dort leer = Multicast).
                "ziel": str(getattr(dev, "port", "") or
                            getattr(dev, "target_ip", "") or
                            getattr(dev, "_target_ip", "") or ""),
                "verbunden": verbunden,
                "problem": problem["text"] if problem else "",
            })
        raus.sort(key=lambda d: (d["universum"], d["weg"]))
        return raus

    def display_snapshot(self) -> dict[int, bytes]:
        """Flache Kopie des Anzeige-Snapshots {universe -> bytes(512)} (POST-
        Master). Kopie des dicts, damit der Aufrufer nicht ueber eine mutierende
        Struktur iteriert; die ``bytes``-Werte selbst sind immutable."""
        return dict(self._display_frame)

    def add_tick_callback(self, cb):
        """Register a callable(dt) that is called each output frame."""
        if cb not in self._tick_callbacks:
            self._tick_callbacks.append(cb)

    def remove_tick_callback(self, cb):
        self._tick_callbacks = [c for c in self._tick_callbacks if c is not cb]

    def set_freeze(self, enabled: bool):
        """BUG-FBW Slice 3: den gesendeten Frame einfrieren.

        Der Renderer steigt im Freeze schon aus (``AppState._render_frame``) —
        das allein reicht aber NICHT: mehrere Wege schreiben **direkt** in die
        Universen, am Renderer vorbei (``_flush_programmer_to_dmx`` bei jedem
        Programmer-Wert, der Input-Merge, Web/OSC-Rohkanaele, Simple Desk). Ohne
        diesen Schnappschuss leckte ein gehaltener Fader durch den Freeze.

        Hier liegt der Schnappschuss VOR Channel-Modifier, Grand-Master,
        Blackout und Laser-NOT-AUS — die vier bleiben also auch eingefroren
        wirksam. Das ist die Eigenschaft, die den Freeze ueberhaupt vertretbar
        macht: er haelt das Bild, aber nie den Notaus.
        """
        if not enabled:
            self._freeze_frames = None
            return
        self._freeze_frames = {u: universe.get_all()
                               for u, universe in list(self.universes.items())}

    @contextmanager
    def lade_sperre(self):
        """OUT-60: waehrend eines Live-Show-Loads den zuletzt gerenderten Stand
        weitersenden.

        Gemessen am echten Enttec (Windows-Rig-PC, 03.10.2026): beim Neu-Laden
        derselben Show fiel in 3 von 8 Laeufen fuer GENAU einen Frame (~23 ms)
        jeder PAR-Dimmer von 255 auf 0 — der 44-Hz-Renderer rechnete mitten im
        reset-first einen Zustand ohne laufende Wiedergabe. CDX-22 hatte nur die
        Adress-Freigabe des Patch-Tauschs gebuendelt, nicht diesen Frame.

        Getrennt vom Bediener-Freeze (``_freeze_frames``): den setzt der
        reset-first selbst zurueck — ein Freeze des Bedieners UEBERSTEHT einen
        Load also NICHT (nach dem Laden laeuft die Ausgabe wieder live). Die
        Sperre darf deshalb nicht am Freeze haengen, sonst fiele sie mitten im
        Load weg. Der Schnappschuss liegt wie beim Freeze VOR Channel-Modifier,
        Grand-Master, Blackout und Laser-NOT-AUS — die greifen also auch
        waehrend des Ladens. Verschachtelt aufrufbar; erst das aeusserste Ende
        gibt frei.

        ★ OUT-60-Folge (Review A): mit eingefroren werden auch die
        PATCH-ABHAENGIGEN Masken — GM-Adressen, Blackout-Erhalten (Pan/Tilt …)
        und gezielter Blackout (VCB-11). Der reset-first baut sie fuer den
        leeren Patch neu; ohne GM-Maske skalierte der Grand-Master dann ALLE
        Kanaele, bei GM < 100 % ruckten Pan/Tilt im Lade-Fenster, und im
        Blackout fielen sie auf 0. GM-Wert und Blackout-Schalter bleiben live.
        Ein Ziel-Blackout (VCB-11), der ERST waehrend des Ladens gedrueckt
        wird, wirkt im Lade-Fenster noch NICHT — es gilt die Ziel-Maske vom
        Start; er greift mit dem ersten Frame nach dem Laden.

        ★ OUT-61 (Review A, Sicherheit): auch die Laser-NOT-AUS-Maske wird
        festgehalten. Der reset-first schob bei aktivem Latch eine LEERE Maske
        (leerer Patch); Ebene 2 des NOT-AUS fiel weg, und ein INVERSE- oder
        Range-Lock-Modifier auf der Laser-Adresse machte aus der 0 im Frame
        eine 255 — Laser AN waehrend des Ladens. Genullt wird die VEREINIGUNG
        aus Start- und Live-Maske: ein waehrend des Ladens ausgeloester NOT-AUS
        wirkt sofort, einer vom Start bleibt bis zum Ende stehen."""
        if self._lade_tiefe == 0:
            frames = {u: universe.get_all()
                      for u, universe in list(self.universes.items())}
            # Die Masken werden immer als Ganzes ersetzt, nie veraendert —
            # die Referenzen festzuhalten genuegt.
            masken = (self._gm_address_mask, self._blackout_keep_mask,
                      getattr(self, "_ziel_blackout_union", None),
                      self._laser_estop_mask,
                      getattr(self, "_laser_adressen", {}) or {},   # OUT-61b
                      getattr(self, "_gm_laser_aus_mask", {}) or {})  # LAS-24
            self._lade = (frames, masken)        # eine Zuweisung = atomar
        self._lade_tiefe += 1
        try:
            yield
        finally:
            self._lade_tiefe -= 1
            if self._lade_tiefe == 0:
                self._lade = None

    @property
    def _lade_frames(self):
        """Lesesicht fuer Tests/Diagnose: eingefrorene Frames der Lade-Sperre."""
        lade = self._lade
        return lade[0] if lade is not None else None

    @property
    def _lade_masken(self):
        """Lesesicht fuer Tests/Diagnose: Masken vom Start der Lade-Sperre."""
        lade = self._lade
        return lade[1] if lade is not None else None

    def set_blackout(self, enabled: bool):
        """Blackout an/aus. UI-58: jede Aenderung wird gemeldet — egal ob sie aus
        der Kopfzeile, einem VC-Taster, Web, OSC oder der Kommandozeile kommt.
        Ohne das zeigte der Kopfzeilen-Knopf nach einer fremden Aenderung den
        alten Stand, und sein naechster Druck machte das Gegenteil (Blackout
        „an" gedrueckt -> nichts wurde dunkel)."""
        enabled = bool(enabled)
        geaendert = enabled != self._blackout
        self._blackout = enabled
        if not geaendert:
            return
        # getattr: Tests bauen den Manager teils per __new__ ohne __init__.
        self._blackout_epoch = getattr(self, "_blackout_epoch", 0) + 1
        for cb in list(self._blackout_callbacks):
            try:
                cb(enabled)
            except Exception:
                pass

    @property
    def blackout(self) -> bool:
        return bool(self._blackout)

    @property
    def blackout_epoch(self) -> int:
        """OUT-57: Zaehler der echten Blackout-Aenderungen (s. ``set_blackout``)."""
        return getattr(self, "_blackout_epoch", 0)

    def subscribe_blackout(self, cb):
        if cb not in self._blackout_callbacks:
            self._blackout_callbacks.append(cb)

    def unsubscribe_blackout(self, cb):
        try:
            self._blackout_callbacks.remove(cb)
        except ValueError:
            pass

    # ── VCB-11: gezielter Blackout ──────────────────────────────────────────

    def set_target_blackout(self, slot, mask: dict[int, frozenset]):
        """VCB-11: Setzt den gezielten Blackout eines Slots (z. B. einer VC-Taste).
        ``mask`` = {universe: Adressen}, die auf 0 gehen. Der Rest des Universums
        laeuft normal weiter. Leere Maske = Slot belegt, wirkt aber auf nichts
        (Ziel ohne gepatchte Geraete — bewusst KEIN globaler Fallback)."""
        clean: dict[int, frozenset] = {}
        for u, addrs in dict(mask or {}).items():
            try:
                fs = frozenset(int(a) for a in addrs if 1 <= int(a) <= 512)
            except (TypeError, ValueError):
                continue
            if fs:
                clean[int(u)] = fs
        self._ziel_blackouts[slot] = clean
        self._ziel_blackout_neu_vereinigen()

    def clear_target_blackout(self, slot):
        """VCB-11: Gibt den gezielten Blackout eines Slots frei (Taste losgelassen,
        geloescht, Show/Seite gewechselt). Unbekannter Slot = no-op."""
        if self._ziel_blackouts.pop(slot, None) is not None:
            self._ziel_blackout_neu_vereinigen()

    def clear_all_target_blackouts(self):
        """VCB-11: Alle gezielten Blackouts freigeben (Show-Wechsel/Reset)."""
        self._ziel_blackouts.clear()
        self._ziel_blackout_neu_vereinigen()

    def target_blackout_slots(self) -> list:
        """VCB-11: Aktuell belegte Slots (fuer Tests/Diagnose)."""
        return list(self._ziel_blackouts.keys())

    def _ziel_blackout_neu_vereinigen(self):
        union: dict[int, set] = {}
        for mask in list(self._ziel_blackouts.values()):
            for u, addrs in mask.items():
                union.setdefault(u, set()).update(addrs)
        # Ein Rutsch, immutable — der Output-Thread sieht alt ODER neu, nie halb.
        self._ziel_blackout_union = {u: frozenset(a) for u, a in union.items() if a}

    def set_submaster(self, slot, level: float, fids=None, heads=None):
        """Setzt einen Submaster-Slot (multiplikativer Dimmer-Faktor 0.0–1.0).
        ``fids=None`` -> GLOBALER Submaster (wirkt auf alle Fixtures, bisheriges
        Verhalten). Ein iterierbares von Fixture-fids beschraenkt den Submaster auf
        genau diese Geraete (zuweisbarer Submaster).

        FM-HEADLAYOUT A4: ``heads={fid: {head, ...}}`` schraenkt den Slot fuer
        DIESE Geraete zusaetzlich auf einzelne Koepfe ein (VC-Submaster pro Kopf).
        Ein Geraet mit Kopf-Einschraenkung zaehlt bewusst NICHT mehr in
        ``submaster_factor_for`` (sonst dimmte ein Kopf-Fader das ganze Geraet) —
        seinen Faktor liefert ``submaster_head_factors_for``. ``heads=None``/leer
        ist exakt das Bestandsverhalten."""
        lvl = max(0.0, min(1.0, float(level)))
        tgt = None if fids is None else frozenset(int(f) for f in fids)
        hd = None
        if heads:
            hd = {}
            for f, hs in dict(heads).items():
                try:
                    fi = int(f)
                except (TypeError, ValueError):
                    continue
                # FM-41: Farbkoepfe als Zahl, Weiss-Segmente als "wN".
                s = frozenset(_kopf_schluessel(h) for h in (hs or ())) - {None}
                if s:
                    hd[fi] = s
            hd = hd or None
        self._submasters[slot] = (lvl, tgt, hd)

    def clear_submaster(self, slot):
        """Entfernt einen Submaster-Slot — z. B. wenn der zugehoerige VC-Fader
        geloescht wird oder den Modus wechselt. Sonst dimmt sein letzter Wert als
        Geist weiter."""
        self._submasters.pop(slot, None)

    def effective_submaster(self) -> float:
        """GLOBALER Submaster-Faktor = Produkt aller GLOBALEN Submaster-Slots
        (target_fids is None), 0.0–1.0. Ohne globalen Submaster: 1.0. Wird vom
        Renderer als multiplikativer Dimmer-Master ueber ALLE Fixtures gelegt
        (EE-02). Zugewiesene (gezielte) Submaster zaehlen hier NICHT mit — die
        liefert ``submaster_factor_for(fid)`` pro Fixture."""
        f = 1.0
        for lvl, tgt, hd in list(self._submasters.values()):
            # Ein kopf-beschraenkter Slot ist NIE global — sonst wuerde ein
            # Kopf-Fader ohne fids-Ziel das gesamte Rig dimmen.
            if tgt is None and not hd:
                f *= max(0.0, min(1.0, lvl))
        return f

    def submaster_factor_for(self, fid) -> float:
        """Produkt aller ZUGEWIESENEN Submaster, deren Ziel-fids ``fid`` enthalten
        (1.0 wenn keiner zutrifft). Multipliziert sich im Renderer mit dem globalen
        Faktor (effective_submaster): ein zugewiesener Submaster dimmt nur seine
        Geraete, kombiniert aber sauber mit Grand-Master und globalem Submaster."""
        try:
            fid = int(fid)
        except (TypeError, ValueError):
            return 1.0
        f = 1.0
        for lvl, tgt, hd in list(self._submasters.values()):
            if tgt is not None and fid in tgt and not (hd and fid in hd):
                f *= max(0.0, min(1.0, lvl))
        return f

    def has_head_submasters(self) -> bool:
        """Gibt es ueberhaupt einen KOPF-beschraenkten Submaster-Slot? Der Renderer
        fragt das EINMAL pro Frame — sonst muesste er ``submaster_head_factors_for``
        fuer jedes Fixture jedes Frames rufen, obwohl der Normalfall „gar keine
        Kopf-Faktoren" ist."""
        for _lvl, _tgt, hd in list(self._submasters.values()):
            if hd:
                return True
        return False

    def submaster_head_factors_for(self, fid) -> dict:
        """FM-HEADLAYOUT A4: ``{head: faktor}`` der KOPF-beschraenkten Submaster-
        Slots fuer dieses Geraet (leeres Dict = keiner, Bestandsfall). Multipliziert
        sich im Renderer auf die kopf-exklusiven Intensitaets-/Farbadressen dieses
        Kopfes — zusaetzlich zu Grand-Master, globalem und geraeteweitem Submaster.

        Geraete OHNE Kopf-Eintrag in einem Slot bleiben unberuehrt; ein Slot mit
        ``fids``-Ziel wirkt nur auf seine Ziel-Geraete (Kopf-Eintraege fremder
        Geraete werden ignoriert)."""
        try:
            fid = int(fid)
        except (TypeError, ValueError):
            return {}
        out: dict = {}
        for lvl, tgt, hd in list(self._submasters.values()):
            if not hd:
                continue
            hs = hd.get(fid)
            if not hs:
                continue
            if tgt is not None and fid not in tgt:
                continue
            v = max(0.0, min(1.0, lvl))
            for h in hs:
                out[h] = out.get(h, 1.0) * v
        return out

    def add_universe(self, number: int) -> Universe:
        u = Universe(number)
        self.universes[number] = u
        return u

    def _swap_device(self, registry: dict, universe: int, new_dev):
        """Tauscht ein Ausgabe-Geraet fuer ein Universe thread-sicher aus und
        schliesst das vorherige. Das (potenziell langsame/blockierende) OEFFNEN
        des neuen Geraets passiert BEWUSST ausserhalb des Locks, damit der
        Output-Thread nicht waehrend eines Serial-/Socket-Open haengt."""
        with self._io_lock:
            old = registry.get(universe)
            registry[universe] = new_dev
        if old is not None:
            try:
                old.close()
            except Exception:
                pass

    def add_enttec(self, universe: int, port: str):
        # Falls derselbe COM-Port bereits auf einem ANDEREN Universe offen ist,
        # zuerst thread-sicher schliessen (ein Port kann nur einmal geoeffnet
        # sein -> sonst "Access denied" beim erneuten Verbinden).
        self.close_enttec_on_port(port)
        self._swap_device(self._enttec_outputs, universe, _make_enttec_device(port))

    def close_enttec_on_port(self, port: str):
        """Schliesst eine evtl. offene Enttec-Verbindung auf diesem COM-Port
        (thread-sicher), egal auf welchem Universe sie haengt."""
        with self._io_lock:
            victims = [(u, d) for u, d in self._enttec_outputs.items()
                       if getattr(d, "port", None) == port]
            for u, _ in victims:
                self._enttec_outputs.pop(u, None)
                self._vergiss_fehler(u)   # OUT-51, s. _vergiss_fehler
        for _, dev in victims:
            try:
                dev.close()
            except Exception:
                pass

    def _set_out_universe(self, universe: int, out_universe):
        """OUT-03: merkt/loescht die konfigurierte externe Universe-Nummer fuer
        ein internes Universum. ``None`` (oder unparsbar) -> Default-Verhalten in
        _send_all (Art-Net num-1, sACN num). Unter Lock, damit _send_all nicht
        mitten im Umschalten liest."""
        with self._io_lock:
            if out_universe is None:
                self._out_universe.pop(universe, None)
                return
            try:
                self._out_universe[universe] = int(out_universe)
            except (TypeError, ValueError):
                self._out_universe.pop(universe, None)

    def add_artnet(self, universe: int, target_ip: str = "255.255.255.255",
                   out_universe=None):
        self._swap_device(self._artnet_outputs, universe, ArtNetSender(target_ip))
        self._set_out_universe(universe, out_universe)

    def add_sacn(self, universe: int, target_ip: str | None = None,
                 out_universe=None):
        neu = SACNSender(target_ip)
        # ★★★ NET-12: den Besitz VOR dem Einhaengen uebernehmen. `_swap_device`
        # schliesst den Vorgaenger unmittelbar danach, und dessen `close()`
        # fragt die QUELLE, ob es einen Nachfolger gibt — nicht die Registry.
        # Ohne diese Zeile wechselt der Besitz erst beim ersten gesendeten
        # Frame des Neuen, und dazwischen schickt der Alte eine
        # Stream-Termination fuer ein weiterlaufendes Universum.
        # Optional aufgerufen, und das ist kein Nachlassen: Art-Net kennt gar
        # keinen Besitz, und die Test-Attrappen ersetzen BEIDE Sender-Klassen
        # durch dieselbe — ein harter Aufruf haette dort einen AttributeError
        # geworfen. Fehlt die Methode, gilt das bisherige Verhalten (eine
        # ueberfluessige Termination), nicht ein Absturz.
        # ⚠️ Damit das keine stille Luecke wird, sichert
        # `test_net12_kein_abbruch_beim_uebernehmen` zu, dass der ECHTE
        # `SACNSender` die Methode hat.
        uebernimm = getattr(neu, "uebernimm", None)
        if uebernimm is not None:
            uebernimm(universe)
        self._swap_device(self._sacn_outputs, universe, neu)
        self._set_out_universe(universe, out_universe)

    #: NET-12: Registry-Name -> Registry-Attribut, fuer ``remove_output(ausser=…)``.
    _REGISTRY_NAMEN = ("enttec", "artnet", "sacn")

    def remove_output(self, universe: int, ausser: str | None = None):
        """OUT-05: entfernt ALLE Ausgabe-Adapter (Enttec/ArtNet/sACN) fuer ein
        Universe thread-sicher und schliesst sie. Noetig fuer Output-Typ-Wechsel und
        "Disabled": frueher schrieben add_enttec/add_artnet/add_sacn nur in ihre
        EIGENE Registry und es gab kein Remove -> nach einem Typ-Wechsel sendete
        _send_all ueber BEIDE Adapter (Doppel-Output), ein "deaktiviertes" Universe
        gab weiter Licht aus, und das Alt-Handle wurde nie geschlossen (Leak).
        pop unter Lock, close ausserhalb (Muster wie _swap_device).

        ★★★ NET-12: ``ausser`` laesst GENAU EINEN Adaptertyp stehen. Das ist kein
        Bequemlichkeits-Schalter, sondern die Voraussetzung dafuer, dass die
        sACN-Uebergabe ueberhaupt greifen kann.

        Hintergrund: ``SACNSender.close`` schickt eine E1.31-Stream-Termination
        (Options-Bit ``0x40``), damit Empfaenger die Quelle sofort verwerfen statt
        2,5 s auf den Network-Data-Loss-Timeout zu warten (OUT-06). Genau
        deswegen fragt sie vorher ``_source.release(...)``: gibt es einen
        Nachfolger, wird NICHT terminiert — ``_swap_device`` haengt den Neuen
        naemlich ein, BEVOR es den Alten schliesst.

        ⚠️ Der Dialog rief bis 2026-09-06 aber ``remove_output(univ)`` UND
        danach ``add_sacn(univ, …)``. Das Entfernen laeuft ueber ``pop`` — im
        Moment des ``close`` steht also KEIN Nachfolger in der Registry, die
        Uebergabe-Sperre kann nicht greifen, und jedes „Uebernehmen" schickt eine
        Termination fuer ein **weiterlaufendes** Universum. Gemessen: 5 von 5
        Uebernahmen mit unveraenderter Konfiguration, 15 von 20 Paketen mit
        gesetztem Termination-Bit. Empfaenger duerfen daraufhin auf ihren
        Fallback gehen — mitten in der Show.

        Mit ``ausser="sacn"`` bleibt der Sender stehen, und das nachfolgende
        ``add_sacn`` tauscht ihn ueber ``_swap_device`` MIT Uebergabe aus. Der
        Grund fuer den Aufruf (MU-01: bei einem Typ-Wechsel muessen die FREMDEN
        Adapter weg, sonst Doppel-Output) bleibt dabei vollstaendig erhalten.
        """
        registries = {"enttec": self._enttec_outputs,
                      "artnet": self._artnet_outputs,
                      "sacn": self._sacn_outputs}
        if ausser is not None and ausser not in registries:
            raise ValueError(f"unbekannter Adaptertyp: {ausser!r}")
        victims = []
        with self._io_lock:
            for name, registry in registries.items():
                if name == ausser:
                    continue
                dev = registry.pop(universe, None)
                if dev is not None:
                    victims.append(dev)
            # OUT-03: eine evtl. konfigurierte externe Universe-Nummer mit
            # entfernen, damit ein spaeter neu angelegter Adapter nicht die alte
            # Nummer erbt.
            #
            # NET-12: bei `ausser` bleibt sie stehen — der ueberlebende Adapter
            # BENUTZT sie, und `add_*` setzt sie unmittelbar danach ohnehin neu.
            # Sie hier zu loeschen waere ein kurzer Zustand, in dem der laufende
            # Sender seine externe Nummer verloren haette.
            if ausser is None:
                self._out_universe.pop(universe, None)
            self._vergiss_fehler(universe)
        for dev in victims:
            try:
                dev.close()
            except Exception:
                pass

    def start(self):
        if self._running and self._thread and self._thread.is_alive():
            return  # bereits laufend -> kein zweiter Thread
        # STAB-04: Ein FRUEHERER Output-Thread kann den stop()-Join-Timeout
        # ueberlebt haben (blockierender Treiber) und noch laufen. Dann KEINEN
        # zweiten Thread daneben starten — zwei Threads wuerden gleichzeitig
        # seriell schreiben (konkurrierende Writes -> Access Violation, Folgebug
        # aus STAB-02). Stattdessen _running reaktivieren: der noch lebende Thread
        # nimmt seine Schleife wieder auf, sobald sein haengendes write()
        # zurueckkommt (Selbstheilung statt Thread-Verdopplung).
        reactivate = self._thread is not None and self._thread.is_alive()
        self._running = True
        if reactivate and self._thread is not None and self._thread.is_alive():
            # Race-Absicherung: _running ist hier BEREITS True gesetzt, bevor wir
            # erneut pruefen. Lebt der Zombie noch, nimmt er seine Schleife wieder
            # auf (kein zweiter Thread). Ist er im engen Fenster doch gerade
            # beendet, fallen wir durch und starten frisch -> nie _running=True
            # ohne laufenden Loop.
            import sys
            print("[OutputManager] frueherer DMX-Output-Thread laeuft noch — "
                  "reaktiviert statt zweiten Thread zu starten (STAB-04).",
                  file=sys.stderr)
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="DMX-Output")
        self._thread.start()

    def stop(self):
        self._running = False
        t = self._thread
        if t is not None:
            # Auf das saubere Thread-Ende WARTEN, bevor wir Geraete schliessen.
            # Ein evtl. haengendes write() loest sich nach spaetestens write_timeout
            # (0.5 s); die 2 s sind reichlich Reserve.
            t.join(timeout=self._stop_join_s)
            if t.is_alive():
                # Thread haengt weiterhin (blockierender Treiber / totes Geraet).
                # Geraete dann BEWUSST NICHT schliessen: ein CloseHandle() neben
                # einem noch laufenden WriteFile loest unter Windows eine Access
                # Violation aus (crash.log 21.+22.06.). Der Prozess endet ohnehin
                # gleich -> das OS gibt den Port frei. Lieber "lecken" als crashen.
                import sys
                print("[OutputManager] DMX-Output-Thread reagiert nicht — direkte "
                      "Geraete bleiben offen (Schutz vor Access Violation beim "
                      "Beenden); prozessisolierte Serial-Worker werden beendet.",
                      file=sys.stderr)
                # STAB-09: Ein EnttecProcessProxy darf hier trotzdem geschlossen
                # werden. Sein send_dmx() blockiert nie im Treiber, sondern
                # schreibt nur in Shared Memory. Ohne diesen expliziten Close
                # ueberlebt der per ``spawn`` gestartete Worker den anschliessenden
                # os._exit()-Pfad als Waise und haelt den USB-Port weiter offen.
                #
                # Bewusst OHNE _io_lock: genau dieser kann vom haengenden Thread
                # gehalten werden. Snapshot/Identity-Pop sind unter dem GIL
                # konsistent; ein bereits gelesener Proxy ignoriert nach close()
                # weitere send_dmx()-Aufrufe. Direkte Serial-/Socket-Geraete
                # bleiben fuer den bisherigen Windows-AV-Schutz unangetastet.
                isolated = []
                for universe, dev in list(self._enttec_outputs.items()):
                    if getattr(dev, "process_isolated", False):
                        if self._enttec_outputs.get(universe) is dev:
                            self._enttec_outputs.pop(universe, None)
                            isolated.append(dev)
                for dev in isolated:
                    try:
                        dev.close()
                    except Exception:
                        pass
                # STAB-04: Referenz auf den noch lebenden Thread BEHALTEN (nicht
                # auf None setzen). Sonst startet ein folgender start() einen
                # zweiten DMX-Thread daneben, der gleichzeitig seriell schreibt
                # (konkurrierende Writes / Access Violation). So erkennt start()
                # den Zombie ueber is_alive() und das naechste stop() joint ihn
                # erneut, sobald sein write() zurueckkommt.
                return
        self._thread = None
        # Thread ist sicher beendet -> kein gleichzeitiges write() mehr moeglich.
        with self._io_lock:
            for registry in (self._enttec_outputs, self._artnet_outputs, self._sacn_outputs):
                for dev in registry.values():
                    try:
                        dev.close()
                    except Exception:
                        pass
                registry.clear()   # zweites stop() -> kein Doppel-Close
            # OUT-51: Mit den Adaptern gehen ihre Fehlerzaehler. Sonst meldete
            # die Statusleiste nach dem Stoppen weiter Ausfaelle von Geraeten,
            # die es nicht mehr gibt.
            self._sende_fehler.clear()

    def _loop(self):
        while self._running:
            t0 = time.perf_counter()
            try:
                self._send_all()
            except Exception as exc:
                # Eine Exception darf den Output-Thread NIE beenden, sonst steht
                # die Ausgabe danach still ohne sichtbaren Grund.
                print(f"[OutputManager] frame error: {exc}")
            elapsed = time.perf_counter() - t0
            sleep = max(0.0, FRAME_INTERVAL - elapsed)
            time.sleep(sleep)

    def _send_all(self):
        """Ein Ausgabe-Frame. Reihenfolge je Universum (verbindlich):

        1. Channel-Modifier (INVERSE, Range-Lock, Kanaltausch);
        2. globaler Blackout (alles ausser Erhalten-Maske auf 0) ODER
           Grand Master (Intensitaets-/Farbadressen skalieren);
        3. Ziel-Blackouts (VCB-11, Licht-Kanaele der Ziel-Geraete auf 0);
        4. Laser-Aus-Werte (LAS-24/LAS-25) bei Blackout, GM < Schwelle oder
           fuer die Adressen eines Ziel-Blackouts — der Aus-Wert ist nicht
           immer 0, deshalb NACH den nullenden Paessen;
        5. Laser-NOT-AUS (A3D-01) als allerletzte Ebene, gewinnt immer.

        Im Lade-Fenster (OUT-60/61) stammen alle Masken aus EINEM gelesenen
        ``_lade``-Tupel."""
        # Drive all registered tick callbacks first (function_manager, etc.).
        # Ueber eine Kopie iterieren: add_/remove_tick_callback laufen im UI-Thread
        # und koennen die Liste waehrenddessen mutieren (list changed size).
        # OUT-51: Ein dauerhaft werfender Tick-Callback heisst, dass Funktionen/
        # Chaser nicht mehr weiterlaufen — die Show steht, ohne dass etwas dunkel
        # wird. Genau der Fall, den man am schwersten erkennt, wenn er still ist.
        #
        # ★ Ueber das FRAME aggregiert, nicht je Callback gebucht: alle Ticks
        # teilen sich einen Zaehler, und mit Buchung je Callback wuerde ein
        # gesunder Nachbar die Serie des kranken bei jedem Frame wieder auf 0
        # setzen — der Zaehler pendelte zwischen 0 und 1 und erreichte die
        # Meldeschwelle nie. Ein Fehler in diesem Frame ist ein Fehler.
        tick_exc = None
        tick_name = ""
        for cb in list(self._tick_callbacks):
            try:
                cb(FRAME_INTERVAL)
            except Exception as exc:
                tick_exc = exc
                # Namen nur im Fehlerfall bestimmen — im Normalbetrieb kostet
                # dieser Block nichts.
                tick_name = getattr(cb, "__qualname__", None) or type(cb).__name__
        if tick_exc is None:
            self._buche_erfolg("Tick", 0)
        else:
            # Derselbe Schluessel wie beim Erfolg — der Name des Callbacks
            # gehoert in den TEXT, nicht in den Schluessel, sonst wuerde die
            # Serie nie zurueckgesetzt.
            self._buche_fehler("Tick", 0, tick_exc, quelle=tick_name)

        # OUT-60: die Lade-Sperre hat Vorrang vor dem Bediener-Freeze.
        lade = self._lade                        # EINMAL lesen (Review A zu #927)
        gefroren = lade[0] if lade is not None else self._freeze_frames
        if lade is not None:
            gm_masken, keep_masken, ziel, estop_start, laser_start = lade[1][:5]
            # LAS-24: Laser-Aus-Maske vom Ladebeginn (im Lade-Fenster ist der
            # Plan leer, die Live-Maske also auch) — vereinigt mit der Live-Maske.
            laser_aus_masken = dict(lade[1][5]) if len(lade[1]) > 5 else {}
            for _u, _m in (getattr(self, "_gm_laser_aus_mask", {}) or {}).items():
                laser_aus_masken[_u] = {**laser_aus_masken.get(_u, {}), **_m}
        else:
            gm_masken, keep_masken = self._gm_address_mask, self._blackout_keep_mask
            laser_aus_masken = getattr(self, "_gm_laser_aus_mask", {}) or {}
            estop_start = None
            laser_start = None
            ziel = getattr(self, "_ziel_blackout_union", None)
        for univ_num, universe in list(self.universes.items()):
            # Im Freeze den festgehaltenen Stand senden statt des (u. U. direkt
            # beschriebenen) Live-Universums. Ein Universum, das es beim
            # Einfrieren noch gar nicht gab, laeuft normal weiter — sonst waere
            # ein frisch hinzugekommener Ausgang dauerhaft stumm.
            data = universe.get_all() if gefroren is None else gefroren.get(
                univ_num, universe.get_all())
            # Channel-Modifier zuerst (vor Grand-Master und Blackout)
            try:
                from src.core.engine.channel_modifier import get_modifier_manager
                data = get_modifier_manager().apply_to_universe(univ_num, data)
            except Exception as exc:
                # OUT-51: Scheitert der Modifier-Pass dauerhaft, gehen INVERSE,
                # Range-Lock und Kanaltausch verloren — das Licht bleibt an,
                # sieht aber falsch aus. Ohne Meldung ist das nicht von einer
                # falsch programmierten Szene zu unterscheiden.
                self._buche_fehler("Modifier", univ_num, exc)
            else:
                self._buche_erfolg("Modifier", univ_num)
            if self._blackout:
                # OUT-57: Blackout nullt ALLES ausser der Erhalten-Maske (Pan/Tilt/
                # Gobo/Prisma/Optik gepatchter Lampen mit echtem Dimmer) — sonst
                # fuhren Moving Heads bei jedem Blackout in die Grundstellung und
                # beim Loesen sichtbar zurueck. Invertiert, damit ungepatchte Roh-
                # Adressen, raw-/Fine-Kanaele und unbekannte Attribute sicher dunkel
                # werden. Der Grand-Master braucht hier nicht mehr zu laufen: seine
                # Adressen sind nie in der Erhalten-Maske (dort steht ohnehin 0).
                keep = keep_masken.get(univ_num)
                buf = bytearray(512)
                if keep:
                    for addr in keep:
                        if 1 <= addr <= len(data) and addr <= 512:
                            buf[addr - 1] = data[addr - 1]
                data = bytes(buf)
            elif self.grand_master < 0.999:
                gm = self.grand_master
                mask = gm_masken.get(univ_num)
                if mask is None:
                    # Ungepatchtes/rohes Universum: kein Adresswissen -> global
                    # dimmen wie bisher (Roh-DMX-Setups behalten ihren GM).
                    data = bytes(min(255, int(b * gm + 0.5)) for b in data)
                else:
                    # Nur Intensitaets-/Farbadressen skalieren; Pan/Tilt/Gobo/
                    # Prism/Shutter bleiben unangetastet (sonst fahren Moving Heads
                    # bei GM<100% auf falsche Positionen — Audit B4).
                    buf = bytearray(data)
                    for addr in mask:
                        if 1 <= addr <= 512:
                            buf[addr - 1] = min(255, int(buf[addr - 1] * gm + 0.5))
                    data = bytes(buf)
            # VCB-11: gezielte Blackouts (VC-Tasten mit Ziel) NACH dem Grand-Master
            # — nur die Licht-Kanaele ihrer Ziel-Geraete auf 0, der Rest laeuft
            # weiter. Beim globalen Blackout ist ohnehin alles ausser der
            # Erhalten-Maske 0; die Ziel-Masken enthalten nie Erhalten-Adressen.
            # getattr: Tests bauen den Manager teils per __new__ ohne __init__.
            ziel_mask = ziel.get(univ_num) if ziel else None
            if ziel_mask and not self._blackout:
                buf = bytearray(data)
                n = len(buf)
                for addr in ziel_mask:
                    if addr <= n:
                        buf[addr - 1] = 0
                data = bytes(buf)
            # LAS-24/LAS-25: Laser-Aus-Werte NACH Blackout und Ziel-Blackout,
            # VOR dem NOT-AUS. Ein Laser ohne Dimmer/Farbe kennt keine
            # Zwischenstufe — Betriebsart/Shutter muessen auf ihren „aus“-Wert,
            # und der ist nicht immer 0 (``range_from`` eines „Laser off“-
            # Bereichs). Bedeutet DMX 0 an diesem Kanal „an/Auto“, wuerde ein
            # Blackout, der hier nur nullt, den Laser EINschalten. Deshalb:
            #   * globaler Blackout oder GM < Schwelle -> alle Aus-Werte;
            #   * Ziel-Blackout -> nur die Aus-Adressen, die der Ziel-Pass
            #     gerade genullt hat (also die Geraete dieses Ziels).
            # Laeuft NACH dem Channel-Modifier (ein INVERSE darf den Laser nicht
            # oeffnen); der NOT-AUS danach zwingt verriegelte Adressen trotzdem
            # auf 0 — der gewinnt immer.
            aus = laser_aus_masken.get(univ_num)
            if aus:
                if self._blackout or self.grand_master < self.GM_LASER_AUS_SCHWELLE:
                    ziel_aus = aus
                elif ziel_mask:
                    ziel_aus = {a: w for a, w in aus.items() if a in ziel_mask}
                else:
                    ziel_aus = None
                if ziel_aus:
                    buf = bytearray(data)
                    n = len(buf)
                    for addr, wert in ziel_aus.items():
                        if 1 <= addr <= n:
                            buf[addr - 1] = wert
                    data = bytes(buf)
            # A3D-01: Laser-NOT-AUS als ALLERLETZTE Ebene — nach Channel-Modifier,
            # Grand-Master UND Blackout die verriegelten Laser-Adressen hart auf 0
            # zwingen. Der Modifier-Pass oben laeuft VOR diesem Schritt und wuerde
            # aus dem im Renderer erzwungenen 0 sonst wieder 255 (INVERSE) bzw.
            # range_min (Range-Lock) machen -> der DMX-Laser bliebe trotz NOT-AUS an.
            # Muss die letzte Transformation vor Anzeige/Senden sein (auch nach GM).
            estop_mask = self._laser_estop_mask.get(univ_num)
            if estop_start:
                # OUT-61: im Lade-Fenster Start- UND Live-Maske (Vereinigung).
                vorher = estop_start.get(univ_num)
                if vorher:
                    estop_mask = set(vorher) | set(estop_mask or ())
            if laser_start and self._laser_estop_aktiv:
                # OUT-61b: Latch erst WAEHREND des Ladens ausgeloest — der Plan ist
                # leer, die Live-Maske also auch. Die Laser-Adressen vom
                # Ladebeginn nullen; der eingefrorene Frame traegt deren Werte.
                vorher = laser_start.get(univ_num)
                if vorher:
                    estop_mask = set(vorher) | set(estop_mask or ())
            if estop_mask:
                buf = bytearray(data)
                for addr in estop_mask:
                    if 1 <= addr <= 512:
                        buf[addr - 1] = 0
                data = bytes(buf)
            # ANZEIGE-Snapshot: exakt die Bytes, die gleich gesendet werden (POST
            # GM/Blackout/Channel-Modifier). GIL-atomare dict-Zuweisung mit
            # immutable ``bytes`` — keine Sperre noetig, Anzeige-Leser sehen immer
            # einen vollstaendigen Frame. NUR fuer die Anzeige, nie zurueckgeschrieben.
            self._display_frame[univ_num] = data
            # Geraete-Zugriff unter Lock: verhindert, dass der UI-Thread ein
            # Geraet schliesst/austauscht, waehrend wir hier senden (Deadlock).
            with self._io_lock:
                enttec = self._enttec_outputs.get(univ_num)
                artnet = self._artnet_outputs.get(univ_num)
                sacn = self._sacn_outputs.get(univ_num)
                # OUT-03: konfigurierte externe Universe-Nummer (falls gesetzt),
                # sonst abwaertskompatibler Default (Art-Net num-1, sACN num).
                ext = self._out_universe.get(univ_num)
                # OUT-51: Die drei Sendeaufrufe fangen weiterhin ALLES — eine
                # Exception darf den Output-Thread nie beenden, sonst steht die
                # ganze Ausgabe. Neu ist nur, dass der Fehler jetzt gezaehlt und
                # bei anhaltendem Ausfall gemeldet wird, statt spurlos zu sein.
                if enttec is not None:
                    try:
                        enttec.send_dmx(data)
                    except Exception as exc:
                        self._buche_fehler("Enttec", univ_num, exc)
                    else:
                        self._buche_erfolg("Enttec", univ_num)
                if artnet is not None:
                    try:
                        artnet.send_dmx(ext if ext is not None else univ_num - 1, data)
                    except Exception as exc:
                        self._buche_fehler("Art-Net", univ_num, exc)
                    else:
                        self._buche_erfolg("Art-Net", univ_num)
                if sacn is not None:
                    try:
                        sacn.send_dmx(ext if ext is not None else univ_num, data)
                    except Exception as exc:
                        self._buche_fehler("sACN", univ_num, exc)
                    else:
                        self._buche_erfolg("sACN", univ_num)
