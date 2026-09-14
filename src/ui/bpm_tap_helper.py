"""TAP mit Doppelrolle (BPM-09, S4): einmal tippen = Beat-Phase auf „jetzt",
mehrfach tippen = Tempo setzen.

- **1. Tipp** (bzw. erster Tipp nach > 2 s Pause): ``det.resync_phase()`` — der
  Beat-Punkt springt auf den Tipp, das Tempo bleibt.
- **2. Tipp**: nur zaehlen — der Manager wird NICHT angetippt (ein Doppelklick
  auf TAP kippt sonst nach MANUELL; plan.md S4: „ab 3. Tipp -> mgr.tap()").
- **ab dem 3. Tipp** innerhalb des 2-s-Fensters: ``mgr.tap()`` (der Manager
  bildet ab seinem 2. Tipp — also dem 4. der Folge — sein Tap-Tempo und geht in
  MANUAL; bpm_manager.py bleibt unangetastet) und ``det.set_tempo_hint(<gemessenes
  Tempo>)`` — die Erkennung sucht danach um dieses Tempo und entscheidet damit
  auch die Oktave. Vier Tipps im Takt = Tempo gesetzt.
- **Ruecksetzen** nach 2 s Pause (gleiches Fenster wie ``BPMManager.TAP_WINDOW_SEC``).

Der Topbar-TAP (main_window.py) und der TAP-Knopf im Tab „Erkennung" rufen
DENSELBEN Helfer (``get_tap_helper()``), damit vier Tipps verteilt auf beide
Knoepfe eine Folge bilden. Manager/Detektor werden nur AUFGERUFEN; fehlt ein
Detektor (numpy fehlt), wirkt nur der Manager-Teil.
"""
from __future__ import annotations
import time

TAP_WINDOW_S = 2.0      # Pause, nach der eine neue Tipp-Folge beginnt
MAX_INTERVALS = 4       # Mittel ueber die letzten 4 Intervalle (wie der Manager)
HINT_FROM_TAP = 3       # ab diesem Tipp der Folge: mgr.tap() + Tempo-Hinweis an den Detektor


class TapHelper:
    """Tipp-Folge → Phase (1. Tipp) bzw. Tempo + Suchhinweis (ab 3. Tipp, Manager-Tempo ab dem 4.)."""

    def __init__(self, mgr=None, det=None, clock=time.monotonic):
        self._mgr = mgr
        self._det = det
        self._clock = clock
        self._taps: list[float] = []

    # ── Backend lazily (Singletons erst beim ersten Tipp aufloesen) ─────────
    def _manager(self):
        if self._mgr is None:
            from src.core.engine.bpm_manager import get_bpm_manager
            self._mgr = get_bpm_manager()
        return self._mgr

    def _detector(self):
        if self._det is None:
            try:
                from src.core.audio.beat_detector import get_beat_detector
                self._det = get_beat_detector()
            except Exception:
                self._det = None
        return self._det

    # ── API ──────────────────────────────────────────────────────────────────
    @property
    def count(self) -> int:
        """Tipps in der laufenden Folge (0 nach Pause/Reset)."""
        return len(self._taps)

    def reset(self):
        self._taps = []

    def measured_bpm(self) -> float:
        """Tempo aus den letzten Intervallen der Folge; 0 bei < 2 Tipps."""
        if len(self._taps) < 2:
            return 0.0
        taps = self._taps[-(MAX_INTERVALS + 1):]
        iv = [b - a for a, b in zip(taps[:-1], taps[1:])]
        avg = sum(iv) / len(iv)
        return 60.0 / avg if avg > 0 else 0.0

    def tap(self) -> float:
        """Ein Tipp. Liefert die Manager-BPM nach dem Tipp (0 solange der
        Manager noch kein Tempo bilden konnte)."""
        now = self._clock()
        if self._taps and (now - self._taps[-1]) > TAP_WINDOW_S:
            self._taps = []
        self._taps.append(now)
        n = len(self._taps)
        det = self._detector()
        if n == 1 and det is not None:
            try:
                det.resync_phase()
            except Exception as e:
                print(f"[TapHelper] resync_phase: {e}")
        bpm = 0.0
        if n < HINT_FROM_TAP:
            return bpm                       # 1./2. Tipp: Phase bzw. nur zaehlen
        try:
            bpm = float(self._manager().tap())
        except Exception as e:
            print(f"[TapHelper] mgr.tap: {e}")
        if det is not None:
            hint = self.measured_bpm()
            if hint > 0:
                try:
                    det.set_tempo_hint(hint)
                except Exception as e:
                    print(f"[TapHelper] set_tempo_hint: {e}")
        return bpm


_helper: TapHelper | None = None


def get_tap_helper() -> TapHelper:
    """Der eine Helfer fuer Topbar-TAP und Tab „Erkennung"."""
    global _helper
    if _helper is None:
        _helper = TapHelper()
    return _helper
