"""BPM-Manager — globaler Tap-Tempo / Beat-Broadcaster.

Funktionsweise:
- Speichert eine globale BPM (0 = aus).
- tap() registriert einen Tap-Zeitstempel, berechnet BPM aus den letzten 4 Intervallen.
- _emit_beat() wird intern alle (60 / BPM) Sekunden aufgerufen und benachrichtigt Subscriber.
- Subscriber registrieren sich via subscribe_beat(callback).

WICHTIG — Threading-Kontrakt: _emit_beat() (und damit die Beat-Callbacks) laeuft
IM HINTERGRUND-THREAD — je nach Quelle im Timer-Thread 'BPM-Beat' oder im
Audio-Capture-Thread, NICHT im Qt-Mainthread. Subscriber, die Qt beruehren,
MUESSEN selbst in den Qt-Thread marshallen (z.B. QTimer.singleShot(0, ...) oder
ein Signal.emit über eine QueuedConnection).
"""
from __future__ import annotations
import time
import threading
from typing import Callable


BeatCallback = Callable[[int], None]   # callback(beat_index)


from enum import Enum


class BpmMode(Enum):
    """Betriebsart des Tempo-Leaders."""
    AUTO = "auto"      # BPM kommt automatisch aus dem Audio-Detektor
    MANUAL = "manual"  # BPM manuell gesetzt (Tap/Nudge/Fader/Eingabe)


class BPMManager:
    """Globaler BPM/Beat-Manager — der zentrale Tempo-„Leader".

    Quellen-Praezedenz: MANUAL (Tap/Nudge/Fader) und LOCK blocken alles; im
    AUTO-Modus treibt der Audio-Detektor (bzw. OS2L/Datei als Fallback) die BPM.
    Es gibt immer GENAU EINE Beat-Quelle: im AUTO-Audio-Modus taktet der
    Audio-Detektor die Beats, sonst der interne Timer-Thread.
    """

    MIN_BPM = 20.0
    MAX_BPM = 999.0
    TAP_WINDOW_SEC = 2.0     # Taps mit >2s Pause starten neue Sequenz
    MAX_TAP_HISTORY = 4      # Mittel ueber die letzten 4 Intervalle

    def __init__(self):
        self._bpm: float = 0.0
        self._last_taps: list[float] = []
        self._beat_callbacks: list[BeatCallback] = []
        self._bpm_change_callbacks: list = []   # callback(bpm: float)
        self._state_callbacks: list = []        # callback() — Modus/Quelle/Lock
        self._timer: threading.Thread | None = None
        self._running: bool = False
        self._beat_index: int = 0
        self._lock = threading.RLock()
        self._audio_active: bool = False
        self._grid_active: bool = False   # taktgenaue Beats aus einem Lied-Beatgrid
        # ── Leader-Zustand ──
        self._mode: BpmMode = BpmMode.AUTO      # AUTO standardmaessig an
        self._locked: bool = False
        self._source: str = "off"               # off|audio|os2l|file|tap|nudge|manual
        self._min_bpm: float = 60.0
        self._max_bpm: float = 200.0
        # ── Takt-Raster ──
        self._beats_per_bar: int = 4    # Schlaege pro Takt (Bar); Downbeat alle N Beats
        self._subdivision: int = 1      # Sub-Ticks pro Beat (1 = aus; nur Timer/Tap/Datei)
        self._tick_index: int = 0
        self._bar_callbacks: list = []   # callback(bar_index)
        self._tick_callbacks: list = []  # callback(tick_index, is_beat)

    # ── Properties ──────────────────────────────────────────────────────────────

    @property
    def bpm(self) -> float:
        return self._bpm

    @property
    def audio_active(self) -> bool:
        """True wenn die BPM gerade aus dem Audio-Eingang kommt (Musik-Modus)."""
        return self._audio_active

    @property
    def mode(self) -> BpmMode:
        return self._mode

    @property
    def current_source(self) -> str:
        return self._source

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def min_bpm(self) -> float:
        return self._min_bpm

    @property
    def max_bpm(self) -> float:
        return self._max_bpm

    @property
    def beats_per_bar(self) -> int:
        return self._beats_per_bar

    @property
    def subdivision(self) -> int:
        return self._subdivision

    def beat_phase_in_bar(self, idx: int) -> int:
        """Position des Beats ``idx`` im Takt (0 = Downbeat)."""
        return idx % max(1, self._beats_per_bar)

    def is_downbeat(self, idx: int) -> bool:
        """True, wenn der Beat ``idx`` der erste Schlag eines Takts ist."""
        return idx % max(1, self._beats_per_bar) == 0

    # ── Grenzen („Hoehen und Tiefen") ──────────────────────────────────────────

    def set_bounds(self, min_bpm: float, max_bpm: float):
        """Setzt die AUTO-Grenzen. Eine autoritative Quelle — wird in den
        Detektor gespiegelt (dort wird oktav-gefaltet/geklemmt)."""
        try:
            lo, hi = float(min_bpm), float(max_bpm)
        except (TypeError, ValueError):
            return
        if lo > hi:
            lo, hi = hi, lo
        lo = max(self.MIN_BPM, min(lo, self.MAX_BPM))
        hi = max(self.MIN_BPM, min(hi, self.MAX_BPM))
        self._min_bpm, self._max_bpm = lo, hi
        try:
            from src.core.audio.beat_detector import get_beat_detector
            get_beat_detector().set_bounds(int(lo), int(hi))
        except Exception as e:
            print(f"[BPMManager] set_bounds detector error: {e}")
        self._emit_state_change()

    def _clamp_bounds(self, bpm: float) -> float:
        return max(self._min_bpm, min(self._max_bpm, bpm))

    # ── Takt-Raster (Bar-Laenge + Unterteilung) ─────────────────────────────────

    def set_beats_per_bar(self, n: int):
        """Schlaege pro Takt (1..64). 4 = Viertakt, 16 = Sechzehntakt. Reine
        Metadaten + Downbeat-/Bar-Event-Raster — aendert NICHT die Beat-Rate."""
        try:
            n = int(n)
        except (TypeError, ValueError):
            return
        n = max(1, min(64, n))
        with self._lock:
            self._beats_per_bar = n
        self._emit_state_change()

    def set_subdivision(self, n: int):
        """Sub-Ticks pro Beat (1..16, 1 = aus). Feinere Aufloesung fuer den
        opt-in Tick-Kanal; greift im Timer/Tap/Datei-Modus (Audio: nur Beat-Rate).
        Die ganzzahligen Musik-Beats (subscribe_beat) bleiben unveraendert."""
        try:
            n = int(n)
        except (TypeError, ValueError):
            return
        n = max(1, min(16, n))
        with self._lock:
            self._subdivision = n
        self._emit_state_change()

    # ── BPM setzen ───────────────────────────────────────────────────────────────

    def set_bpm(self, bpm: float, source: str | None = None):
        """Tiefer, geklemmter Setter. 0 = aus. source=None laesst die Quelle
        unveraendert (Alt-Verhalten: aendert NICHT Modus/Quelle — dafuer sonst
        request_bpm()/tap()/nudge()). Wird source uebergeben, schreibt der Setter
        _source UND _bpm unter EINEM Lock-Hold (atomar).

        CDX-14: Die internen Aufrufer (_set_manual/request_bpm) setzten _source
        frueher in einem SEPARATEN Lock-Fenster und danach _bpm hier — ein
        reset() dazwischen (setzt _source='off', _bpm=0) hinterliess einen
        inkonsistenten Zustand _bpm>0 bei _source='off'. Source jetzt atomar mit
        _bpm zu setzen schliesst dieses Fenster."""
        if bpm < 0:
            bpm = 0
        if bpm > 0 and (bpm < self.MIN_BPM or bpm > self.MAX_BPM):
            bpm = max(self.MIN_BPM, min(self.MAX_BPM, bpm))
        # A3D-17 + CDX-14: _bpm, optionale _source und das abgeleitete 'off' unter
        # EINEM Lock schreiben — sonst kann dieser (oft aus dem Audio-Thread
        # aufgerufene) Setter den unter dem Lock nullenden reset() ueberholen und
        # einen inkonsistenten Zustand hinterlassen (_bpm>0 bei _source='off'). Der
        # BPM-04-Lock in reset() wirkt nur, wenn auch der Gegen-Writer den Lock nimmt.
        with self._lock:
            self._bpm = float(bpm)
            if source is not None:
                self._source = source
            if self._bpm <= 0:
                self._source = "off"
        self._sync_emitter()
        self._emit_bpm_change()

    def _set_manual(self, bpm: float, source: str):
        """Manuelle Uebersteuerung (Tap/Nudge/Fader/Eingabe) → MANUAL-Modus."""
        with self._lock:
            self._mode = BpmMode.MANUAL
        # CDX-14: _source atomar mit _bpm setzen (nicht mehr in separatem
        # Lock-Fenster vor set_bpm, in das ein reset() schluepfen koennte).
        self.set_bpm(bpm, source=source)
        self._emit_state_change()

    def request_bpm(self, bpm: float, source: str = "audio"):
        """BPM-Anfrage einer NICHT-manuellen Quelle (OS2L/Datei) mit Praezedenz.
        MANUAL/Lock blocken; und im AUTO-Modus hat der laufende Audio-Detektor
        Vorrang vor OS2L/Datei (zentrale Praezedenz statt konkurrierender Writer)."""
        if self._locked or self._mode == BpmMode.MANUAL:
            return
        # Audio-Detektor ist im AUTO-Modus die fuehrende Quelle.
        if self._audio_active and source != "audio":
            return
        # CDX-14: _source atomar mit _bpm setzen (kein separates _source-Lock-Fenster
        # mehr, in das ein reset() schluepfen und _bpm>0 bei _source='off' hinterlassen
        # koennte).
        self.set_bpm(bpm, source=source)
        self._emit_state_change()

    def tap(self) -> float:
        """Tap-Tempo: BPM ueber die letzten 4 Taps. → MANUAL-Modus.
        Returns: aktuelle BPM (0 falls noch zu wenig Taps)."""
        now = time.monotonic()
        with self._lock:
            if self._last_taps and (now - self._last_taps[-1] > self.TAP_WINDOW_SEC):
                self._last_taps = []
            self._last_taps.append(now)
            if len(self._last_taps) > self.MAX_TAP_HISTORY + 1:
                self._last_taps = self._last_taps[-(self.MAX_TAP_HISTORY + 1):]
            if len(self._last_taps) < 2:
                return 0.0
            intervals = [self._last_taps[i + 1] - self._last_taps[i]
                         for i in range(len(self._last_taps) - 1)]
            avg = sum(intervals) / len(intervals)
            if avg <= 0:
                return 0.0
            bpm = 60.0 / avg
        self._set_manual(bpm, "tap")
        return self._bpm

    def nudge(self, delta_bpm: float) -> float:
        """Manuelles Nachziehen um ±delta_bpm. Aktiviert MANUAL."""
        base = self._bpm
        if base <= 0:
            try:
                from src.core.audio.beat_detector import get_beat_detector
                base = get_beat_detector().get_bpm() or 120.0
            except Exception:
                base = 120.0
        self._set_manual(base + float(delta_bpm), "nudge")
        return self._bpm

    def set_manual_bpm(self, bpm: float):
        """Oeffentlicher manueller Setter (Top-Bar-Eingabe / VC-Fader) → MANUAL."""
        self._set_manual(float(bpm), "manual")

    def set_mode(self, mode):
        """Betriebsart AUTO/MANUAL umschalten (akzeptiert BpmMode oder str)."""
        if isinstance(mode, str):
            mode = BpmMode.AUTO if mode.lower() == "auto" else BpmMode.MANUAL
        with self._lock:
            self._mode = mode
        self._sync_emitter()
        self._emit_state_change()

    def set_locked(self, locked: bool):
        """Lock: friert die BPM ein (Auto-Quellen koennen sie nicht aendern)."""
        with self._lock:
            self._locked = bool(locked)
        self._emit_state_change()

    def reset(self):
        """Schaltet BPM aus."""
        # BPM-04 / A3D-17: _bpm MUSS unter dem Lock genullt werden — sonst kann ein
        # paralleler set_bpm() (Audio-Thread) den Reset ueberholen und einen
        # inkonsistenten Zustand hinterlassen (_bpm>0 bei _source='off'). Seit A3D-17
        # nimmt set_bpm() den Lock ebenfalls, sodass die Serialisierung wirklich
        # greift (vorher schuetzte der Lock hier nur eine Haelfte der Race).
        # HINWEIS: reset() laesst _mode==AUTO — laufende AUTO-Quellen (Audio-Detektor,
        # OS2L, Timeline, File, TempoBus) re-setzen _bpm beim naechsten Event wieder
        # ('BPM springt zurueck'). Ob ein manuelles '0'/reset ALLE Live-Quellen
        # ueberstimmen soll (und den Modus auf MANUAL flippen), ist eine offene
        # Verhaltensentscheidung -> BACKLOG A3D-17b (nicht hier geraten).
        with self._lock:
            self._last_taps = []
            self._beat_index = 0
            self._tick_index = 0
            self._source = "off"
            self._grid_active = False
            self._bpm = 0.0
        self._stop_timer()
        self._emit_bpm_change()
        self._emit_state_change()

    # ── Subscriber ───────────────────────────────────────────────────────────────

    def subscribe_beat(self, cb: BeatCallback):
        if cb not in self._beat_callbacks:
            self._beat_callbacks.append(cb)

    def unsubscribe_beat(self, cb: BeatCallback):
        if cb in self._beat_callbacks:
            self._beat_callbacks.remove(cb)

    def subscribe_bpm_change(self, cb):
        """Callback(bpm) wird bei jeder BPM-Aenderung aufgerufen (Tap/Set/Audio)."""
        if cb not in self._bpm_change_callbacks:
            self._bpm_change_callbacks.append(cb)

    def unsubscribe_bpm_change(self, cb):
        if cb in self._bpm_change_callbacks:
            self._bpm_change_callbacks.remove(cb)

    def subscribe_state_change(self, cb):
        """Callback() bei Aenderung von Modus/Quelle/Lock/Grenzen."""
        if cb not in self._state_callbacks:
            self._state_callbacks.append(cb)

    def unsubscribe_state_change(self, cb):
        if cb in self._state_callbacks:
            self._state_callbacks.remove(cb)

    def subscribe_bar(self, cb):
        """Callback(bar_index) bei jedem Downbeat (erster Schlag eines Takts).
        Das Takt-Raster richtet sich nach ``beats_per_bar`` ("16er-Takt")."""
        if cb not in self._bar_callbacks:
            self._bar_callbacks.append(cb)

    def unsubscribe_bar(self, cb):
        if cb in self._bar_callbacks:
            self._bar_callbacks.remove(cb)

    def subscribe_tick(self, cb):
        """Callback(tick_index, is_beat) fuer den feinen Unterteilungs-Raster.
        Feuert ``subdivision`` mal pro Beat (Timer/Tap/Datei); ``is_beat`` ist
        True genau auf den ganzzahligen Musik-Beats."""
        if cb not in self._tick_callbacks:
            self._tick_callbacks.append(cb)

    def unsubscribe_tick(self, cb):
        if cb in self._tick_callbacks:
            self._tick_callbacks.remove(cb)

    def _emit_bpm_change(self):
        for cb in list(self._bpm_change_callbacks):
            try:
                cb(self._bpm)
            except Exception as e:
                print(f"[BPMManager] bpm-change callback error: {e}")

    def _emit_state_change(self):
        for cb in list(self._state_callbacks):
            try:
                cb()
            except Exception as e:
                print(f"[BPMManager] state callback error: {e}")

    def _emit_bar(self, bar_index: int):
        for cb in list(self._bar_callbacks):
            try:
                cb(bar_index)
            except Exception as e:
                print(f"[BPMManager] bar callback error: {e}")

    def _emit_tick(self, is_beat: bool):
        idx = self._tick_index
        for cb in list(self._tick_callbacks):
            try:
                cb(idx, is_beat)
            except Exception as e:
                print(f"[BPMManager] tick callback error: {e}")
        self._tick_index += 1

    def _emit_beat(self):
        # BPM-01: Laeuft im HINTERGRUND-THREAD (Timer 'BPM-Beat' bzw.
        # Audio-Capture-Thread), NICHT im Qt-Mainthread. Die Beat-Callbacks werden
        # direkt hier synchron aufgerufen — jeder Subscriber, der Qt beruehrt, muss
        # selbst marshallen (QTimer.singleShot / Signal.emit). Kein Marshalling hier,
        # um das praezise Beat-Timing nicht zu stoeren.
        idx = self._beat_index
        for cb in list(self._beat_callbacks):
            try:
                cb(idx)
            except Exception as e:
                print(f"[BPMManager] beat callback error: {e}")
        self._beat_index += 1
        # Downbeat/Bar-Event alle beats_per_bar Schlaege (konfigurierbares Raster).
        bpb = max(1, self._beats_per_bar)
        if idx % bpb == 0:
            self._emit_bar(idx // bpb)
        # Plus: Audio-triggered Chasers automatisch weiterschalten
        try:
            from src.core.engine.function_manager import get_function_manager
            from src.core.engine.chaser import Chaser
            fm = get_function_manager()
            for f in fm.all():
                if (isinstance(f, Chaser) and f.is_running
                        and getattr(f, 'audio_triggered', False)):
                    f.trigger_next_step()
        except Exception:
            pass
        # Plus: Beat-synchrone Cuelisten taktgenau weiterschalten (on_beat zaehlt
        # selbst die beats_per_cue und triggert nur die aktive, beat_sync-Liste).
        try:
            from src.core.app_state import get_state
            for stack in list(getattr(get_state(), "cue_stacks", []) or []):
                if getattr(stack, "beat_sync", False):
                    stack.on_beat()
        except Exception:
            pass

    # ── Audio-Quelle ─────────────────────────────────────────────────────────────

    def use_audio_source(self, enabled: bool):
        """Toggle: BPM aus Audio-Capture statt Tap-Tempo. Aktiviert AUTO."""
        if enabled:
            try:
                from src.core.audio.capture import get_audio_capture
                from src.core.audio.beat_detector import get_beat_detector
                cap = get_audio_capture()
                det = get_beat_detector()
                cap.subscribe(det.process_chunk)
                det.subscribe(self._on_audio_beat)
                cap.start()
                self._audio_active = True
                with self._lock:
                    self._mode = BpmMode.AUTO
            except Exception as e:
                print(f"[BPMManager] use_audio_source error: {e}")
        else:
            if self._audio_active:
                try:
                    from src.core.audio.beat_detector import get_beat_detector
                    det = get_beat_detector()
                    det.unsubscribe(self._on_audio_beat)
                    # Capture laeuft weiter falls andere Subscriber existieren
                except Exception as e:
                    print(f"[BPMManager] use_audio_source off error: {e}")
                self._audio_active = False
        self._sync_emitter()
        self._emit_state_change()

    def _on_audio_beat(self):
        """Beat vom AudioDetector (laeuft im Audio-Thread)."""
        try:
            from src.core.audio.beat_detector import get_beat_detector
            det = get_beat_detector()
            self._apply_detected_bpm(det.get_bpm())
            # Im AUTO-Audio-Modus ist der Detektor die EINZIGE Beat-Quelle
            if self._audio_is_emitter():
                self._emit_beat()
                self._emit_tick(True)   # Tick-Kanal bei Audio: nur Beat-Rate
        except Exception as e:
            print(f"[BPMManager] audio beat error: {e}")

    def _apply_detected_bpm(self, bpm: float):
        """Erkannte BPM uebernehmen — nur in AUTO, nicht gelockt, in Grenzen."""
        if self._locked or self._mode != BpmMode.AUTO:
            return
        if bpm <= 0:
            return
        bpm = self._clamp_bounds(bpm)
        # CDX-14: _source atomar mit _bpm setzen (nicht in einem separaten Lock-Fenster
        # vor set_bpm) — der Audio-Pfad ist der haeufigste Gegenspieler von reset(),
        # sonst bliebe genau hier das Fenster _bpm>0 bei _source='off' offen.
        self.set_bpm(bpm, source="audio")

    # ── Beat-Emitter (genau eine Quelle: Timer XOR Audio XOR Grid) ──────────────

    def _audio_is_emitter(self) -> bool:
        """True wenn der Audio-Detektor (AUTO) die Beats taktet → kein Timer."""
        return self._audio_active and self._mode == BpmMode.AUTO

    def _grid_is_emitter(self) -> bool:
        """True wenn ein Beatgrid (Lied-Analyse) die Beats taktgenau treibt."""
        return self._grid_active and self._mode == BpmMode.AUTO

    def _external_is_emitter(self) -> bool:
        """Audio ODER Grid taktet die Beats → der interne Timer pausiert."""
        return self._audio_is_emitter() or self._grid_is_emitter()

    @property
    def grid_active(self) -> bool:
        return self._grid_active

    def use_grid_source(self, enabled: bool):
        """Toggle: Beats kommen TAKTGENAU aus einem Lied-Beatgrid (statt vom
        freilaufenden Timer). Aktiviert AUTO; der Treiber ruft ``emit_grid_beat()``.
        Der Timer pausiert, solange das Grid die Quelle ist."""
        with self._lock:
            self._grid_active = bool(enabled)
            if enabled:
                self._mode = BpmMode.AUTO
        self._sync_emitter()
        self._emit_state_change()

    def emit_grid_beat(self, is_downbeat: bool = False):
        """Vom Beatgrid-Treiber aufgerufen: feuert EINEN taktgenauen Beat (nur wenn
        das Grid die aktive Quelle ist). ``is_downbeat`` richtet die Bar-Phase am
        echten Lied-Downbeat aus, damit Bar-/Downbeat-Events zum Lied passen."""
        if not self._grid_is_emitter():
            return
        if is_downbeat:
            bpb = max(1, self._beats_per_bar)
            with self._lock:
                self._beat_index -= self._beat_index % bpb
        self._emit_beat()
        self._emit_tick(True)

    def _sync_emitter(self):
        """Sorgt dafuer, dass GENAU EINE Beat-Quelle laeuft (Timer XOR Audio XOR
        Grid). Entscheidung + Timer-Start/Stop laufen unter dem RLock, damit
        konkurrierende Aufrufer (UI-/Audio-/OS2L-/Grid-Thread) nie zwei Timer starten."""
        with self._lock:
            if self._external_is_emitter():
                self._stop_timer()
            elif self._bpm > 0:
                self._ensure_running()
            else:
                self._stop_timer()

    # ── Timer-Thread ─────────────────────────────────────────────────────────────

    def _ensure_running(self):
        # Wird unter self._lock aufgerufen (siehe _sync_emitter).
        if self._running:
            return
        self._running = True
        self._timer = threading.Thread(target=self._loop, daemon=True, name="BPM-Beat")
        self._timer.start()

    def _stop_timer(self):
        with self._lock:
            self._running = False
            self._timer = None

    def _loop(self):
        me = threading.current_thread()
        next_tick = time.monotonic()
        sub = 0   # Sub-Tick-Zaehler innerhalb eines Beats (fuer subdivision)
        # `self._timer is me` stellt sicher, dass ein evtl. verdraengter (alter)
        # Timer-Thread keinen Beat mehr feuert — nur der aktuell registrierte.
        while (self._running and self._timer is me and self._bpm > 0
               and not self._external_is_emitter()):
            now = time.monotonic()
            subdiv = max(1, self._subdivision)
            interval = 60.0 / max(self._bpm, 1.0) / subdiv
            if now >= next_tick:
                # Direkt vor dem Emit erneut pruefen (Fenster gegen Doppel-Beat
                # beim Umschalten auf eine externe Quelle / Stop).
                if (not self._running or self._timer is not me
                        or self._external_is_emitter()):
                    break
                is_beat = (sub % subdiv == 0)
                if is_beat:                     # ganzzahliger Musik-Beat
                    self._emit_beat()
                self._emit_tick(is_beat)        # jeder Sub-Tick (opt-in Kanal)
                sub = (sub + 1) % subdiv
                next_tick += interval
                # Falls weit hinterher (z.B. nach Pause), resync (+ Downbeat neu)
                if now - next_tick > interval:
                    next_tick = now + interval
                    sub = 0
            sleep = max(0.001, next_tick - time.monotonic())
            time.sleep(min(0.05, sleep))


# ── Singleton ─────────────────────────────────────────────────────────────────

_mgr: BPMManager | None = None


def get_bpm_manager() -> BPMManager:
    global _mgr
    if _mgr is None:
        _mgr = BPMManager()
    return _mgr
