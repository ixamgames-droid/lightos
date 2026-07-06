"""LaserOutputManager (LAS-05/06) — eigener Streaming-Thread für Netzwerk-Laser.

Bewusst GETRENNT von der 44-Hz-DMX-Pipeline (``OutputManager``): Punktlisten
sind strukturell keine 512-Byte-Universen. Geteilt wird nur der Lifecycle
(Start in ``AppState.start_playback``, Stop im MainWindow-Shutdown) und das
Safety-Verhalten: BLACKOUT des OutputManagers blankt hier JEDEN Frame vor dem
Senden (Galvos laufen weiter, kein Lichtaustritt), zusätzlich gibt es einen
verriegelnden Not-Aus (:meth:`estop_all`/:meth:`clear_estop_all`).

Zwei Backends hinter derselben Connection-Schnittstelle (stream_frame/estop/
clear_estop/stop/close + ``.host``): Ether Dream (``protocol=='etherdream'``,
TCP) und IDN (``protocol=='idn'``, UDP, LAS-06). Die Protokoll-Weiche sitzt in
:meth:`_conn_for`; alles andere ist backend-neutral.

v1-Framequelle: ein Testmuster (Kreis) aus den Programmer-Werten des
Fixtures — shutter (An/Aus), laser_x/laser_y (Position), zoom (Größe),
color_r/g/b (Farbe), laser_draw (sichtbarer Anteil). Der freie Zeichenmodus
(LAS-07) ersetzt diese Quelle später durch echte Punktlisten; die
:func:`~src.core.laser.frame.clamp_frame`-Stufe bleibt davor Pflicht.
"""
from __future__ import annotations

import math
import threading
import time

from .etherdream import EtherDreamConnection, EtherDreamError
from .idn import IDNConnection, IDNError
from .frame import LaserFrame, LaserLimits, LaserPoint, clamp_frame

_RETRY_SECONDS = 2.0

# Protokoll → Connection-Fehler, den ein Tick als „Gerät weg" behandelt.
_CONN_ERRORS = (EtherDreamError, IDNError, OSError)

# Netzwerk-Protokolle, die der LaserOutputManager bedient.
_STREAM_PROTOCOLS = ("etherdream", "idn")


def _prog_value(state, fid: int, attr: str, default: int) -> int:
    try:
        v = state.get_programmer_value(fid, attr)
    except Exception:
        v = None
    if v is None:
        return default
    try:
        return max(0, min(255, int(v)))
    except (TypeError, ValueError):
        return default


def build_test_frame(state, fx, limits: LaserLimits, fps: int) -> LaserFrame:
    """Kreis-Testmuster aus den Programmer-Werten des Netzwerk-Lasers.

    Punktzahl = pps/fps, damit der DAC-Puffer im Gleichgewicht bleibt
    (jeder Tick liefert genau eine Frame-Periode an Punkten)."""
    fid = int(getattr(fx, "fid", 0) or 0)
    pps = min(20000, int(limits.max_pps))
    n = max(int(limits.min_points), min(int(limits.max_points), pps // max(1, fps)))

    # Shutter-Gate: unter 128 bleibt der Frame komplett dunkel — deckt den
    # Laser-Safety-Default (Shutter 0 beim Patchen) ab.
    lit = _prog_value(state, fid, "shutter", 0) >= 128
    cx = (_prog_value(state, fid, "laser_x", 128) - 128) / 127.0
    cy = (_prog_value(state, fid, "laser_y", 128) - 128) / 127.0
    radius = _prog_value(state, fid, "zoom", 128) / 255.0
    r = _prog_value(state, fid, "color_r", 255) / 255.0
    g = _prog_value(state, fid, "color_g", 255) / 255.0
    b = _prog_value(state, fid, "color_b", 255) / 255.0
    draw = _prog_value(state, fid, "laser_draw", 255) / 255.0

    points = []
    for i in range(n):
        t = i / n
        ang = t * 2.0 * math.pi
        points.append(LaserPoint(
            x=cx + radius * math.cos(ang),
            y=cy + radius * math.sin(ang),
            r=r, g=g, b=b,
            blanked=(not lit) or (t > draw),
        ))
    return LaserFrame(points=points, pps=pps)


class LaserOutputManager:
    """Hält je Netzwerk-Laser (fid) eine DAC-Verbindung und schiebt pro Tick
    einen geclampten Frame. Verbindungsfehler werfen nie in den Thread —
    betroffene Geräte bekommen einen Reconnect-Backoff."""

    TARGET_FPS = 30

    def __init__(self, state):
        self._state = state
        self.limits = LaserLimits()
        # Pro Protokoll eine Factory (Tests überschreiben sie mit Fakes).
        # `connection_factory` bleibt als Ether-Dream-Alias für Rückwärts-
        # kompatibilität bestehender Tests erhalten.
        self.connection_factory = EtherDreamConnection
        self.idn_connection_factory = IDNConnection
        self._connections: dict[int, object] = {}
        # Protokoll je offener Verbindung — im Manager geführt (nicht am
        # Connection-Objekt), damit ein Protokollwechsel erkannt wird, ohne
        # auf Attribut-Zuweisbarkeit des Backends/Fakes angewiesen zu sein.
        self._conn_proto: dict[int, str] = {}
        self._retry_at: dict[int, float] = {}
        self._estopped = False
        # LAS-07 Safety: Laser-Ausgabe startet UNSCHARF. Solange nicht scharf
        # geschaltet, wird JEDER Streaming-Frame geblankt (Vorschau ohne
        # Lichtaustritt) — der freie Zeichenmodus darf erst nach bewusstem
        # Arming echtes Licht ausgeben. Gilt global für alle Netzwerk-Laser.
        self._armed = False
        # Aktive gezeichnete Figur je fid (LaserFigure). Ohne Eintrag fällt der
        # Tick auf das Kreis-Testmuster (build_test_frame) zurück.
        self._figures: dict[int, object] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────
    @property
    def running(self) -> bool:
        return self._running

    @property
    def estopped(self) -> bool:
        return self._estopped

    # ── Safety: Scharfschalten ────────────────────────────────────────────
    @property
    def armed(self) -> bool:
        return self._armed

    def set_armed(self, value: bool):
        """Scharf/unscharf schalten. Unscharf blankt die Ausgabe ab dem
        NÄCHSTEN Tick — ein bereits laufender Tick kann noch mit dem alten
        Wert fertig senden, d. h. garantiert dunkel spätestens nach einer
        Tick-Periode (~1/TARGET_FPS ≈ 33 ms). Für sofortiges Dunkel: estop_all."""
        changed = self._armed != bool(value)
        self._armed = bool(value)
        if changed:
            self._notify_armed_changed()

    def _notify_armed_changed(self):
        """Anzeige-Sync (LAS-10): Laser-Steuerseite + VC-Buttons erfahren eine
        Scharf/Unscharf-Änderung von irgendeiner Quelle (LaserView, VC, MIDI),
        damit kein Safety-Indikator stale „unscharf" zeigt, während scharf."""
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.LASER_ARMED_CHANGED, self._armed)
        except Exception:
            pass

    def set_figure(self, fid: int, figure):
        """Gezeichnete Figur als Framequelle für ein Fixture setzen (``None``
        entfernt sie → zurück zum Testmuster)."""
        with self._lock:
            if figure is None:
                self._figures.pop(int(fid), None)
            else:
                self._figures[int(fid)] = figure

    def clear_figures(self):
        with self._lock:
            self._figures.clear()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="Laser-Output", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=2.0)
        self._thread = None
        with self._lock:
            conns = list(self._connections.values())
            self._connections.clear()
            self._conn_proto.clear()
        for conn in conns:
            try:
                conn.stop()
            except Exception:
                pass
            conn.close()

    # ── Not-Aus (verriegelnd, unabhängig vom BLACKOUT) ────────────────────
    def estop_all(self):
        # Flag ZUERST (der Tick-Thread hört sofort auf zu senden), dann die
        # Netzwerk-Befehle AUSSERHALB des Locks — I/O unterm Lock würde den
        # Tick-Thread (und damit weitere Geräte) bis zum Timeout blockieren.
        self._estopped = True
        with self._lock:
            conns = list(self._connections.values())
        for conn in conns:
            try:
                conn.estop()
            except Exception:
                conn.close()
        # UXT-12: auch DMX-Muster-Laser (L2600 & Co.) hart dunkel schalten — der
        # obige Netzwerk-Estop erreicht sie nicht. Latch im State setzen; der
        # Renderer zwingt deren Kanäle dann auf 0, bis bewusst ein neuer Laser-
        # Wert gesetzt wird.
        try:
            self._state.set_laser_estop(True)
        except Exception:
            pass
        # UXT-09: zentrale, unmissverständliche NOT-AUS-Bestätigung — egal ob von
        # der Laser-Steuerseite oder einem VC-Button ausgelöst (beide gehen hier
        # durch). Das Hauptfenster zeigt darauf einen prominenten Hinweis.
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.LASER_ESTOP, None)
        except Exception:
            pass

    def clear_estop_all(self):
        with self._lock:
            conns = list(self._connections.values())
        for conn in conns:
            try:
                conn.clear_estop()
            except Exception:
                conn.close()
        self._estopped = False

    # ── Tick ──────────────────────────────────────────────────────────────
    def _network_fixtures(self) -> list:
        out = []
        try:
            fixtures = self._state.get_patched_fixtures()
        except Exception:
            return out
        for f in fixtures:
            proto = (getattr(f, "protocol", "") or "").lower()
            host = (getattr(f, "net_host", "") or "").strip()
            if proto in _STREAM_PROTOCOLS and host:
                out.append(f)
        return out

    def _factory_for(self, proto: str):
        if proto == "idn":
            return self.idn_connection_factory
        return self.connection_factory   # etherdream (Default)

    def _conn_for(self, fx):
        fid = int(getattr(fx, "fid", 0) or 0)
        host = (getattr(fx, "net_host", "") or "").strip()
        proto = (getattr(fx, "protocol", "") or "").lower()
        with self._lock:
            conn = self._connections.get(fid)
            # Neu verbinden, wenn Host ODER Protokoll gewechselt hat.
            stale = conn is not None and (
                conn.host != host or self._conn_proto.get(fid) != proto)
            if stale:
                conn.close()
                conn = None
                self._connections.pop(fid, None)
                self._conn_proto.pop(fid, None)
            if conn is None:
                if time.monotonic() < self._retry_at.get(fid, 0.0):
                    return None
                conn = self._factory_for(proto)(host)
                self._connections[fid] = conn
                self._conn_proto[fid] = proto
        return conn

    def _blackout_active(self) -> bool:
        try:
            return bool(getattr(self._state.output_manager, "_blackout", False))
        except Exception:
            return False

    def _frame_for(self, fx, fid: int) -> LaserFrame:
        """Framequelle für ein Fixture: aktive gezeichnete Figur (per Programmer
        laser_x/y/zoom positioniert/skaliert), sonst das Kreis-Testmuster."""
        figure = self._figures.get(fid)
        if figure is None:
            return build_test_frame(self._state, fx, self.limits,
                                    self.TARGET_FPS)
        pps = min(20000, int(self.limits.max_pps))
        n = max(int(self.limits.min_points),
                min(int(self.limits.max_points), pps // max(1, self.TARGET_FPS)))
        ox = (_prog_value(self._state, fid, "laser_x", 128) - 128) / 127.0
        oy = (_prog_value(self._state, fid, "laser_y", 128) - 128) / 127.0
        scale = _prog_value(self._state, fid, "zoom", 255) / 255.0
        lit = _prog_value(self._state, fid, "shutter", 0) >= 128
        frame = figure.to_frame(n, pps, offset_x=ox, offset_y=oy, scale=scale)
        # Shutter-Gate wie beim Testmuster: unter 128 komplett dunkel.
        return frame if lit else frame.blank_copy()

    def _tick(self):
        fixtures = self._network_fixtures()
        if not fixtures:
            return
        # Nicht scharf geschaltet ⇒ Ausgabe geblankt (LAS-07-Safety), ebenso
        # bei BLACKOUT oder aktivem Not-Aus.
        dark = self._blackout_active() or self._estopped or not self._armed
        for fx in fixtures:
            conn = self._conn_for(fx)
            if conn is None:
                continue
            fid = int(getattr(fx, "fid", 0) or 0)
            frame = self._frame_for(fx, fid)
            if dark:
                frame = frame.blank_copy()
            frame = clamp_frame(frame, self.limits)
            try:
                if self._estopped:
                    # Verriegelt: nichts senden (DAC ist per estop() gestoppt).
                    continue
                conn.stream_frame(frame)
                self._retry_at.pop(fid, None)
            except _CONN_ERRORS:
                conn.close()
                with self._lock:
                    self._connections.pop(fid, None)
                    self._conn_proto.pop(fid, None)
                self._retry_at[fid] = time.monotonic() + _RETRY_SECONDS

    def _loop(self):
        interval = 1.0 / float(self.TARGET_FPS)
        while self._running:
            t0 = time.monotonic()
            try:
                self._tick()
            except Exception as e:   # Thread darf NIE sterben
                print(f"[laser_output] tick error: {e}")
            rest = interval - (time.monotonic() - t0)
            if rest > 0:
                time.sleep(rest)
