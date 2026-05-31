"""BPM-Manager — globaler Tap-Tempo / Beat-Broadcaster.

Funktionsweise:
- Speichert eine globale BPM (0 = aus).
- tap() registriert einen Tap-Zeitstempel, berechnet BPM aus den letzten 4 Intervallen.
- _emit_beat() wird intern alle (60 / BPM) Sekunden aufgerufen und benachrichtigt Subscriber.
- Subscriber registrieren sich via subscribe_beat(callback). Callback wird im Qt-Mainthread aufgerufen.
"""
from __future__ import annotations
import time
import threading
from typing import Callable


BeatCallback = Callable[[int], None]   # callback(beat_index)


class BPMManager:
    """Globaler BPM/Beat Manager."""

    MIN_BPM = 20.0
    MAX_BPM = 999.0
    TAP_WINDOW_SEC = 2.0     # Taps mit >2s Pause starten neue Sequenz
    MAX_TAP_HISTORY = 4      # Mittel ueber die letzten 4 Intervalle

    def __init__(self):
        self._bpm: float = 0.0
        self._last_taps: list[float] = []
        self._beat_callbacks: list[BeatCallback] = []
        self._bpm_change_callbacks: list = []   # callback(bpm: float)
        self._timer: threading.Thread | None = None
        self._running: bool = False
        self._beat_index: int = 0
        self._lock = threading.RLock()
        self._audio_active: bool = False

    # ── BPM ───────────────────────────────────────────────────────────────────

    @property
    def bpm(self) -> float:
        return self._bpm

    def set_bpm(self, bpm: float):
        """Setzt BPM manuell. 0 = aus."""
        if bpm < 0:
            bpm = 0
        if bpm > 0 and (bpm < self.MIN_BPM or bpm > self.MAX_BPM):
            bpm = max(self.MIN_BPM, min(self.MAX_BPM, bpm))
        self._bpm = float(bpm)
        if self._bpm > 0:
            self._ensure_running()
        else:
            self._stop_timer()
        self._emit_bpm_change()

    def tap(self) -> float:
        """Tap-Tempo: Speichert Zeitstempel, errechnet BPM ueber die letzten 4 Taps.
        Returns: aktuelle BPM (0 falls noch zu wenig Taps)."""
        now = time.monotonic()
        with self._lock:
            # Wenn lange keine Taps -> neu starten
            if self._last_taps and (now - self._last_taps[-1] > self.TAP_WINDOW_SEC):
                self._last_taps = []
            self._last_taps.append(now)
            # Nur die letzten N+1 behalten (fuer N Intervalle)
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
        self.set_bpm(bpm)
        return self._bpm

    def reset(self):
        """Schaltet BPM aus."""
        with self._lock:
            self._last_taps = []
            self._beat_index = 0
        self._bpm = 0.0
        self._stop_timer()
        self._emit_bpm_change()

    # ── Beat-Subscriber ───────────────────────────────────────────────────────

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

    def _emit_bpm_change(self):
        for cb in list(self._bpm_change_callbacks):
            try:
                cb(self._bpm)
            except Exception as e:
                print(f"[BPMManager] bpm-change callback error: {e}")

    def _emit_beat(self):
        idx = self._beat_index
        for cb in list(self._beat_callbacks):
            try:
                cb(idx)
            except Exception as e:
                print(f"[BPMManager] beat callback error: {e}")
        self._beat_index += 1
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

    # ── Audio Source ──────────────────────────────────────────────────────────

    def use_audio_source(self, enabled: bool):
        """Toggle: BPM aus Audio-Capture statt Tap-Tempo."""
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
            except Exception as e:
                print(f"[BPMManager] use_audio_source error: {e}")
        else:
            if self._audio_active:
                try:
                    from src.core.audio.capture import get_audio_capture
                    from src.core.audio.beat_detector import get_beat_detector
                    cap = get_audio_capture()
                    det = get_beat_detector()
                    det.unsubscribe(self._on_audio_beat)
                    # Capture laufen lassen falls andere subscriber existieren
                except Exception as e:
                    print(f"[BPMManager] use_audio_source off error: {e}")
                self._audio_active = False

    def _on_audio_beat(self):
        """Beat vom AudioDetector."""
        try:
            from src.core.audio.beat_detector import get_beat_detector
            det = get_beat_detector()
            bpm = det.get_bpm()
            if bpm > 0:
                self._bpm = float(max(self.MIN_BPM, min(self.MAX_BPM, bpm)))
            # Direkt Beat emittieren (synchron zum erkannten Audio-Beat)
            self._emit_beat()
        except Exception as e:
            print(f"[BPMManager] audio beat error: {e}")

    # ── Timer-Thread ──────────────────────────────────────────────────────────

    def _ensure_running(self):
        if self._running:
            return
        self._running = True
        self._timer = threading.Thread(target=self._loop, daemon=True, name="BPM-Beat")
        self._timer.start()

    def _stop_timer(self):
        self._running = False
        self._timer = None

    def _loop(self):
        next_beat = time.monotonic()
        while self._running and self._bpm > 0:
            now = time.monotonic()
            interval = 60.0 / max(self._bpm, 1.0)
            if now >= next_beat:
                self._emit_beat()
                next_beat += interval
                # Falls weit hinterher (z.B. nach Pause), resync
                if now - next_beat > interval:
                    next_beat = now + interval
            sleep = max(0.001, next_beat - time.monotonic())
            time.sleep(min(0.05, sleep))


# ── Singleton ─────────────────────────────────────────────────────────────────

_mgr: BPMManager | None = None


def get_bpm_manager() -> BPMManager:
    global _mgr
    if _mgr is None:
        _mgr = BPMManager()
    return _mgr
