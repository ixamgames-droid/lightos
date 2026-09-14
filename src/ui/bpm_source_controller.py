"""Quellen-Umschalter der BPM-Erkennung (BPM-09, S4) — EINE Stelle fuer alles,
was ein Eintrag der Quelle-Combo im Tab „Erkennung" schaltet.

Je Eintrag (``kind``, ``device``):

| kind        | Capture                              | OS2L   | Manager                                    |
|-------------|--------------------------------------|--------|--------------------------------------------|
| ``loopback``| ``set_source_mode("loopback", sink)``| stop   | ``use_audio_source(True)`` (startet Capture)|
| ``input``   | ``set_source_mode("input", device)`` | stop   | ``use_audio_source(True)``                 |
| ``os2l``    | stop                                 | start  | ``use_audio_source(False)``                |
| ``song``    | stop                                 | stop   | ``use_audio_source(False)`` + aktueller Player-Track (``request_bpm``, nur in AUTO) |
| ``off``     | stop                                 | stop   | ``use_audio_source(False)``                |

``sink`` (S5) ist die ``sink_id`` eines Ausgabegeraets aus
``AudioCapture.list_loopback_sinks()``; alles andere (z. B. ein Mikrofonname aus
alten Einstellungen) wird zu None = Standard-Ausgabegeraet — ein Eingangsname
darf den Loopback nie aufs Mikrofon lenken.

Bei JEDEM Wechsel: ``det.set_tempo_hint(None)`` (Suche wieder frei) und
``det.reset()`` (alter Tempo-Zustand gehoert zur alten Quelle). Der Manager-
Modus (AUTO/MANUAL) haengt NICHT an der Quelle: ``use_audio_source(True)``
erzwingt AUTO, danach wird der vorherige Modus wiederhergestellt (S2-Lehre:
Capture haengt an der Quelle, der Modus am Manager).

**Idempotent:** derselbe Eintrag zweimal hintereinander schaltet nichts ein
zweites Mal (S2-Befund: Radio-Wechsel feuerte doppelt und startete den Capture
zweimal). ``apply`` liefert False, wenn nichts zu tun war.

Auto | Manuell (``set_auto``): Auto = ``mgr.set_mode("auto")`` und — falls die
Quelle Audio ist und der Manager sie nicht mehr hoert — ``use_audio_source(True)``;
bei Quelle ``song`` wird der Player-Track erneut angeboten. Manuell =
``mgr.set_mode("manual")``; der Capture laeuft weiter (Erkennung im Hintergrund
sichtbar, Rueckweg auf Auto sofort).

×½ / ×2 (``octave``): in AUTO ``det.set_octave_preference(-1/+1)``, in MANUAL
``mgr.set_manual_bpm(bpm/2 bzw. bpm*2)``. S6 (BPM-11): in AUTO wird vorher der
Tempo-Bereich geprueft (``mgr.min_bpm``/``max_bpm``) — liegt das Ziel ausserhalb,
passiert NICHTS und ``octave`` liefert ``(False, Grund)``; der Bereich wird nie
stumm veraendert (ui_diagnose 5.4). Die View zeigt den Grund als Statuszeilen-
Ereignis.

Fehlender Sink (S6): wird PC-Audio mit einer ``sink_id`` gewaehlt, die es gerade
nicht gibt, laeuft der Capture auf dem Standard-Ausgabegeraet; ``missing_sink``
nennt dann die gewuenschte id (Statuszeile), sonst None.

Backends werden nur AUFGERUFEN (bpm_manager.py, capture.py, os2l.py,
beat_detector.py bleiben unangetastet); jeder Schritt ist einzeln abgesichert,
damit ein fehlendes Backend (kein soundcard/numpy) die uebrigen nicht blockiert.
"""
from __future__ import annotations

AUDIO_KINDS = ("loopback", "input")


def _known_sink(device: str | None) -> str | None:
    """``device`` nur zurueckgeben, wenn es eine aktuelle ``sink_id`` ist."""
    if not device:
        return None
    try:
        from src.core.audio.capture import AudioCapture
        ids = {str(i) for i, _n in (AudioCapture.list_loopback_sinks() or [])}
    except Exception:
        return None
    return device if device in ids else None
KINDS = ("loopback", "input", "os2l", "song", "off")


def _log(msg: str) -> None:
    print(f"[SourceController] {msg}")


def _is_auto(mgr) -> bool:
    """AUTO-Modus des Managers (BpmMode oder str, fuer Fakes in Tests)."""
    m = getattr(mgr, "mode", None)
    return str(getattr(m, "name", m)).lower() == "auto"


class SourceController:
    """Schaltet Capture / OS2L / Manager je Quelle — genau eine Stelle, idempotent."""

    def __init__(self, mgr=None, cap=None, os2l=None, det=None, player=None):
        self._mgr, self._cap, self._os2l, self._det, self._player = mgr, cap, os2l, det, player
        self._current: tuple[str, str | None] | None = None
        self.missing_sink: str | None = None

    # ── Backends lazily (Singletons; Tests reichen Fakes herein) ────────────
    def _manager(self):
        if self._mgr is None:
            from src.core.engine.bpm_manager import get_bpm_manager
            self._mgr = get_bpm_manager()
        return self._mgr

    def _capture(self):
        if self._cap is None:
            try:
                from src.core.audio.capture import get_audio_capture
                self._cap = get_audio_capture()
            except Exception as e:
                _log(f"kein Capture: {e}")
        return self._cap

    def _server(self):
        if self._os2l is None:
            try:
                from src.core.audio.os2l import get_os2l_server
                self._os2l = get_os2l_server()
            except Exception as e:
                _log(f"kein OS2L: {e}")
        return self._os2l

    def _detector(self):
        if self._det is None:
            try:
                from src.core.audio.beat_detector import get_beat_detector
                self._det = get_beat_detector()
            except Exception:
                self._det = None
        return self._det

    def _media(self):
        if self._player is None:
            try:
                from src.core.audio.media_player import get_media_player
                self._player = get_media_player()
            except Exception as e:
                _log(f"kein Player: {e}")
        return self._player

    # ── API ──────────────────────────────────────────────────────────────────
    @property
    def current(self) -> tuple[str, str | None] | None:
        """Zuletzt angewandter Eintrag ``(kind, device)`` oder None."""
        return self._current

    @property
    def kind(self) -> str | None:
        return self._current[0] if self._current else None

    def is_audio(self) -> bool:
        return self.kind in AUDIO_KINDS

    def apply(self, kind: str, device: str | None = None, force: bool = False) -> bool:
        """Quelle schalten. Liefert False, wenn der Eintrag schon aktiv war (idempotent)."""
        if kind not in KINDS:
            _log(f"unbekannte Quelle {kind!r} ignoriert")
            return False
        if kind not in AUDIO_KINDS:
            device = None
        wanted = device
        if kind == "loopback":
            device = _known_sink(device)   # nur echte sink_id, sonst Standard-Ausgabegeraet
        key = (kind, device)
        if key == self._current and not force:
            return False
        self._current = key
        self.missing_sink = wanted if (kind == "loopback" and wanted and device is None) else None
        mgr = self._manager()
        det = self._detector()
        if det is not None:
            self._safe("tempo_hint", lambda: det.set_tempo_hint(None))
            self._safe("reset", det.reset)
        if kind in AUDIO_KINDS:
            self._os2l_stop()
            cap = self._capture()
            if cap is not None:
                self._safe("set_source_mode", lambda: cap.set_source_mode(kind, device))
            mode_before = mgr.mode
            self._safe("use_audio_source", lambda: mgr.use_audio_source(True))
            self._safe("set_mode", lambda: mgr.set_mode(mode_before))
        else:
            self._safe("use_audio_source", lambda: mgr.use_audio_source(False))
            self._capture_stop()
            if kind == "os2l":
                srv = self._server()
                if srv is not None and not srv.is_running():
                    self._safe("os2l start", srv.start)
            else:
                self._os2l_stop()
            if kind == "song":
                self.apply_player_track()
        return True

    def set_auto(self, auto: bool) -> None:
        """Zweizustand Auto | Manuell (der Manager-Modus, unabhaengig von der Quelle)."""
        mgr = self._manager()
        if auto:
            self._safe("set_mode auto", lambda: mgr.set_mode("auto"))
            if self.is_audio() and not getattr(mgr, "audio_active", False):
                self._safe("use_audio_source", lambda: mgr.use_audio_source(True))
            elif self.kind == "song":
                self.apply_player_track()
        else:
            self._safe("set_mode manual", lambda: mgr.set_mode("manual"))

    def octave_target(self, step: int) -> float:
        """Tempo, auf das ×½ (step < 0) / ×2 (step > 0) fuehren wuerde (0 = unbekannt)."""
        mgr = self._manager()
        bpm = float(getattr(mgr, "bpm", 0.0) or 0.0)
        if bpm <= 0 and _is_auto(mgr):
            det = self._detector()
            try:
                bpm = float(det.snapshot().bpm) if det is not None else 0.0
            except Exception:
                bpm = 0.0
        if bpm <= 0:
            return 0.0
        return bpm / 2.0 if step < 0 else bpm * 2.0

    def octave(self, step: int) -> tuple[bool, str | None]:
        """×½ (step < 0) / ×2 (step > 0): in AUTO Oktav-Vorzug des Detektors, in
        MANUAL das manuelle Tempo halbieren/verdoppeln. Liefert ``(True, None)``
        oder ``(False, Grund)``, wenn das Ziel in AUTO ausserhalb des Tempo-Bereichs
        liegt (dann kein Aufruf)."""
        mgr = self._manager()
        if _is_auto(mgr):
            ziel = self.octave_target(step)
            lo = float(getattr(mgr, "min_bpm", 0.0) or 0.0)
            hi = float(getattr(mgr, "max_bpm", 0.0) or 0.0)
            if ziel > 0 and hi > lo and not (lo <= ziel <= hi):
                knopf = "×2" if step > 0 else "×½"
                return False, (f"{knopf} nicht möglich: {ziel:.0f} BPM außerhalb des "
                               f"Tempo-Bereichs {lo:.0f}–{hi:.0f}")
            det = self._detector()
            if det is not None:
                self._safe("set_octave_preference",
                           lambda: det.set_octave_preference(-1 if step < 0 else 1))
        else:
            bpm = float(mgr.bpm or 0.0)
            if bpm > 0:
                self._safe("set_manual_bpm",
                           lambda: mgr.set_manual_bpm(bpm / 2.0 if step < 0 else bpm * 2.0))
        return True, None

    def apply_player_track(self) -> float:
        """Quelle „Lied-Analyse": den AKTUELLEN Player-Track als Timeline-Quelle
        anbieten (Median der Analyse als Start-BPM, ``request_bpm`` greift nur in
        AUTO). Liefert die angebotene BPM (0 = kein analysierter Track)."""
        mp = self._media()
        if mp is None:
            return 0.0
        try:
            t = mp.current_track
            if t is None or not getattr(t, "bpm_timeline", None):
                return 0.0
            from src.core.audio.offline_timeline import BpmTimeline
            med = float(BpmTimeline.from_dict(t.bpm_timeline or {}).summary().get("median", 0) or 0)
            if med > 0:
                self._manager().request_bpm(med, "timeline")
            return med
        except Exception as e:
            _log(f"Player-Track: {e}")
            return 0.0

    # ── intern ───────────────────────────────────────────────────────────────
    def _os2l_stop(self):
        srv = self._server()
        if srv is not None and srv.is_running():
            self._safe("os2l stop", srv.stop)

    def _capture_stop(self):
        cap = self._capture()
        if cap is not None and cap.is_running():
            self._safe("capture stop", cap.stop)

    @staticmethod
    def _safe(what: str, fn) -> None:
        try:
            fn()
        except Exception as e:
            _log(f"{what}: {e}")


_controller: SourceController | None = None


def get_source_controller() -> SourceController:
    """Der eine Umschalter fuer den Tab „Erkennung" (und Auto-Start)."""
    global _controller
    if _controller is None:
        _controller = SourceController()
    return _controller
