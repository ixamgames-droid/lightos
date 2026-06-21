"""MusicShowDirector — koppelt den In-App-Musik-Player an eine Auto-Lichtshow.

Ist die Kopplung aktiv (``state.music_autoshow["enabled"]``), startet beim Play im
``MediaPlayer`` automatisch die konfigurierten Funktionen (``function_ids``) — eine
BPM-synchrone Lichtshow — und stoppt sie beim Pause/Stop. So läuft beim Drücken von
„▶" im Musik-Player (oder am Bank-1-Play-Pad) automatisch eine passende Show mit.

BPM-Quelle bleibt VirtualDJ→OS2L bzw. Tap/Audio; der Director stellt nur sicher, dass
überhaupt ein BPM-Takt läuft (Nominal-BPM des Tracks, sonst 120 als Fallback), damit
beat-getriggerte Chaser/Cuelisten sofort mitlaufen.

Singleton, einmalig in ``main_window`` per ``get_music_director().attach()`` verdrahtet.
Liest ``state.music_autoshow`` bei jedem Play **live** — ein Show-Wechsel wirkt also sofort.
Headless-/Test-tauglich: alle Engine-Imports sind lazy.
"""
from __future__ import annotations
import time
import bisect

from PySide6.QtCore import QObject, QTimer


class MusicShowDirector(QObject):
    """Startet/stoppt die Auto-Lichtshow synchron zum In-App-Player."""

    def __init__(self):
        super().__init__()
        self._attached = False
        self._started_ids: list[int] = []
        self._per_track_ids: list[int] = []    # AUTODJ-(a): aktueller Per-Song-Look
        # BPM-Generator: gecachte Timeline des aktuellen Tracks + zuletzt
        # geschobene BPM (gegen Spam bei jedem positionChanged-Tick).
        self._tl = None
        self._tl_key = None
        self._last_timeline_bpm: float = 0.0
        # Phase 2: taktgenaue Beat-Wiedergabe aus dem Beatgrid.
        self._phase_accurate: bool = True
        self._grid_timer = None
        self._grid_on: bool = False
        self._grid_beats: list = []
        self._grid_downbeats: set = set()
        self._grid_anchor_pos: float = 0.0
        self._grid_anchor_wall: float = 0.0
        self._grid_next_i: int = 0

    # ── Taktgenaue Wiedergabe an/aus (user-steuerbar) ───────────────────────────
    def set_phase_accurate(self, on: bool):
        self._phase_accurate = bool(on)
        if not on:
            self._grid_stop()

    def is_phase_accurate(self) -> bool:
        return self._phase_accurate

    # ── Anbindung ───────────────────────────────────────────────────────────────
    def attach(self):
        """Verbindet sich (idempotent) mit dem globalen MediaPlayer."""
        if self._attached:
            return
        try:
            from src.core.audio.media_player import get_media_player
            mp = get_media_player()
            mp.playingChanged.connect(self._on_playing)
            mp.trackChanged.connect(self._on_track_changed)
            mp.positionChanged.connect(self._on_position)
            # Schneller Timer interpoliert die Beats zwischen den groben
            # positionChanged-Updates (taktgenaue Wiedergabe).
            self._grid_timer = QTimer(self)
            self._grid_timer.setInterval(15)
            self._grid_timer.timeout.connect(self._grid_tick)
            self._attached = True
        except Exception as e:
            print(f"[MusicShowDirector] attach error: {e}")

    # ── Konfiguration ───────────────────────────────────────────────────────────
    def _config(self) -> dict:
        try:
            from src.core.app_state import get_state
            cfg = getattr(get_state(), "music_autoshow", None) or {}
        except Exception:
            cfg = {}
        slots = {}
        for k, v in (cfg.get("slots") or {}).items():
            try:
                slots[int(k)] = str(v)
            except (TypeError, ValueError):
                pass
        return {
            "enabled": bool(cfg.get("enabled", False)),
            "function_ids": [int(x) for x in (cfg.get("function_ids") or [])],
            "bank": int(cfg.get("bank", 0) or 0),
            "slots": slots,
        }

    def is_enabled(self) -> bool:
        return self._config()["enabled"]

    # ── Signale vom MediaPlayer ─────────────────────────────────────────────────
    def _on_playing(self, playing: bool):
        if playing:
            self.start_show()
        else:
            self.stop_show()
            self._grid_stop()      # Pause/Stop → taktgenaue Wiedergabe anhalten

    def _on_track_changed(self, _idx: int):
        # Trackwechsel: Timeline-Cache + Beatgrid-Treiber invalidieren.
        self._last_timeline_bpm = 0.0
        self._grid_stop()
        # Trackwechsel während laufender Auto-Show: BPM-Fallback nachziehen, damit
        # die Effekte zur neuen Nominal-BPM takten (OS2L/Tap/Audio haben Vorrang).
        # AUTODJ-(a): zusätzlich den Per-Song-Look austauschen.
        try:
            from src.core.audio.media_player import get_media_player
            mp = get_media_player()
            if not (mp.is_playing and self.is_enabled()):
                return
            self._ensure_bpm()
            self._stop_track_functions()
            t = mp.current_track
            ids = list(getattr(t, "autoshow_function_ids", []) or []) if t else []
            if ids:
                self._start_track_functions(ids)
        except Exception:
            pass

    # ── BPM-Generator: Timeline → globale BPM (Wert) + taktgenaue Beats (Grid) ───
    def _on_position(self, pos_ms: int, _dur_ms: int = 0):
        """Treibt aus der Lied-Analyse des aktuellen Tracks: (1) den BPM-WERT
        (für Top-Bar/Busse) und (2) — wenn ein echtes Beatgrid vorliegt und es
        führen darf — TAKTGENAUE Beats über den schnellen Timer.

        Präzedenz: MANUAL/Lock und aktiver Live-Audio gewinnen weiter; daher führt
        die Analyse nur, wenn der Nutzer „Lied-Analyse" gewählt hat (Live-Audio aus)."""
        try:
            from src.core.audio.media_player import get_media_player
            mp = get_media_player()
            if not getattr(mp, "couple_bpm", True):
                self._grid_stop()
                return
            tl = self._timeline_for(mp.current_track)
            if tl is None or tl.is_empty():
                self._grid_stop()
                return
            from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
            mgr = get_bpm_manager()
            can_lead = (not mgr.is_locked and mgr.mode == BpmMode.AUTO
                        and not mgr.audio_active)
            # (1) BPM-Wert setzen (nur bei Änderung, gegen Spam)
            bpm = tl.bpm_at(pos_ms)
            if bpm > 0 and abs(bpm - self._last_timeline_bpm) >= 0.5:
                self._last_timeline_bpm = bpm
                mgr.request_bpm(bpm, "timeline")
            # (2) Taktgenaue Beats aus dem Grid (re-ankern bei jedem Update)
            if (self._phase_accurate and can_lead and tl.has_grid()
                    and getattr(mp, "is_playing", False)):
                self._grid_arm(tl, pos_ms)
            else:
                self._grid_stop()
        except Exception:
            pass

    # ── Taktgenaue Beat-Wiedergabe (Grid-Treiber) ───────────────────────────────
    def _grid_arm(self, tl, pos_ms: int):
        """(Re-)Ankert das Beatgrid an der aktuellen Wiedergabe-Position. Der
        schnelle Timer interpoliert ab hier per Wall-Clock bis zum nächsten Update."""
        beats = tl.beats_ms or []
        if len(beats) < 2:
            self._grid_stop()
            return
        self._grid_beats = beats
        self._grid_downbeats = set(tl.downbeats_ms or [])
        self._grid_anchor_pos = float(pos_ms)
        self._grid_anchor_wall = time.monotonic()
        self._grid_next_i = bisect.bisect_right(beats, pos_ms)
        if not self._grid_on:
            try:
                from src.core.engine.bpm_manager import get_bpm_manager
                get_bpm_manager().use_grid_source(True)
            except Exception:
                pass
            self._grid_on = True
            if self._grid_timer is not None:
                self._grid_timer.start()

    def _grid_tick(self):
        """15-ms-Tick: feuert alle Grid-Beats, die seit dem letzten Tick fällig
        wurden (geschätzte Position = Anker + verstrichene Wall-Clock-Zeit)."""
        if not self._grid_on or not self._grid_beats:
            return
        try:
            from src.core.engine.bpm_manager import get_bpm_manager
            mgr = get_bpm_manager()
            est = self._grid_anchor_pos + (time.monotonic() - self._grid_anchor_wall) * 1000.0
            beats = self._grid_beats
            n = len(beats)
            i = self._grid_next_i
            # Großer Rückstand (Seek/Lag) → überspringen statt nachfeuern
            if i < n and est - beats[i] > 700:
                i = bisect.bisect_right(beats, est)
            fired = 0
            while i < n and beats[i] <= est and fired < 8:
                mgr.emit_grid_beat(is_downbeat=(beats[i] in self._grid_downbeats))
                i += 1
                fired += 1
            self._grid_next_i = i
        except Exception:
            pass

    def _grid_stop(self):
        """Hält die taktgenaue Wiedergabe an und gibt die Beat-Quelle frei."""
        if not self._grid_on:
            return
        self._grid_on = False
        if self._grid_timer is not None:
            self._grid_timer.stop()
        try:
            from src.core.engine.bpm_manager import get_bpm_manager
            get_bpm_manager().use_grid_source(False)
        except Exception:
            pass

    def _timeline_for(self, track):
        """Cached BpmTimeline des aktuellen Tracks (Rebuild bei Trackwechsel)."""
        if track is None:
            return None
        data = getattr(track, "bpm_timeline", None)
        if not data:
            self._tl, self._tl_key = None, None
            return None
        if self._tl_key != track.path:
            try:
                from src.core.audio.offline_timeline import BpmTimeline
                self._tl = BpmTimeline.from_dict(data)
            except Exception:
                self._tl = None
            self._tl_key = track.path
        return self._tl

    # ── Show steuern ────────────────────────────────────────────────────────────
    def start_show(self):
        """Startet die konfigurierten Auto-Show-Funktionen (No-op wenn aus/leer)."""
        cfg = self._config()
        if not cfg["enabled"] or not cfg["function_ids"]:
            return
        self._ensure_bpm()
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            started: list[int] = []
            for fid in cfg["function_ids"]:
                if fm.get(fid) is not None:
                    fm.start(fid)
                    started.append(fid)
            self._started_ids = started
            # Live-Edit-Slots der gestarteten Funktionen setzen, damit Bank-Pads
            # desselben Slots sie sauber ablösen (layer-getrennt, ohne stop_all).
            slots = cfg.get("slots") or {}
            if slots:
                try:
                    from src.core.engine import effect_live
                    for fid in started:
                        slot = slots.get(fid)
                        if slot:
                            effect_live.set_edit_target(slot, fid)
                except Exception:
                    pass
        except Exception as e:
            print(f"[MusicShowDirector] start error: {e}")
        # AUTODJ-(a): zusätzlich den Per-Song-Look des aktuellen Tracks starten.
        try:
            from src.core.audio.media_player import get_media_player
            t = get_media_player().current_track
            ids = list(getattr(t, "autoshow_function_ids", []) or []) if t else []
            if ids:
                self._start_track_functions(ids)
        except Exception:
            pass

    def _start_track_functions(self, ids: list[int]):
        """AUTODJ-(a): die Per-Song-Look-Funktionen eines Tracks starten."""
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            started: list[int] = []
            for fid in ids:
                if fm.get(fid) is not None:
                    fm.start(fid)
                    started.append(fid)
            self._per_track_ids = started
            slots = self._config().get("slots") or {}
            if slots:
                try:
                    from src.core.engine import effect_live
                    for fid in started:
                        slot = slots.get(fid)
                        if slot:
                            effect_live.set_edit_target(slot, fid)
                except Exception:
                    pass
        except Exception as e:
            print(f"[MusicShowDirector] per-track start error: {e}")

    def _stop_track_functions(self):
        """AUTODJ-(a): den aktuellen Per-Song-Look stoppen. Funktionen, die auch zur
        globalen Auto-Show (``function_ids``) gehören, bleiben laufen (die owned
        ``stop_show``)."""
        if not self._per_track_ids:
            return
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            global_ids = set(self._config().get("function_ids") or [])
            for fid in self._per_track_ids:
                if fid not in global_ids:
                    fm.stop(fid)
        except Exception as e:
            print(f"[MusicShowDirector] per-track stop error: {e}")
        self._per_track_ids = []

    def stop_show(self):
        """Stoppt die Auto-Show-Funktionen (zuletzt gestartete + aktuell konfigurierte)."""
        self._stop_track_functions()       # AUTODJ-(a): Per-Song-Look zuerst
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            ids = set(self._config()["function_ids"]) | set(self._started_ids)
            for fid in ids:
                fm.stop(fid)
        except Exception as e:
            print(f"[MusicShowDirector] stop error: {e}")
        self._started_ids = []

    def _ensure_bpm(self):
        """Sorgt dafür, dass ein BPM-Takt läuft (sonst stehen Beat-Effekte still).
        OS2L/Tap/Audio haben Vorrang; nur wenn noch keine BPM gesetzt ist, wird die
        Nominal-BPM des aktuellen Tracks (sonst 120) verwendet."""
        try:
            from src.core.engine.bpm_manager import get_bpm_manager
            bm = get_bpm_manager()
            if bm.bpm > 0:
                return
            bpm = 120.0
            try:
                from src.core.audio.media_player import get_media_player
                t = get_media_player().current_track
                if t is not None and t.bpm > 0:
                    bpm = float(t.bpm)
            except Exception:
                pass
            bm.request_bpm(bpm, "file")
        except Exception as e:
            print(f"[MusicShowDirector] bpm error: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────────

_director: MusicShowDirector | None = None


def get_music_director() -> MusicShowDirector:
    global _director
    if _director is None:
        _director = MusicShowDirector()
    return _director
