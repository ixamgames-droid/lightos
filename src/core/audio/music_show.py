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

from PySide6.QtCore import QObject


class MusicShowDirector(QObject):
    """Startet/stoppt die Auto-Lichtshow synchron zum In-App-Player."""

    def __init__(self):
        super().__init__()
        self._attached = False
        self._started_ids: list[int] = []

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

    def _on_track_changed(self, _idx: int):
        # Trackwechsel während laufender Auto-Show: BPM-Fallback nachziehen, damit
        # die Effekte zur neuen Nominal-BPM takten (OS2L/Tap/Audio haben Vorrang).
        try:
            from src.core.audio.media_player import get_media_player
            if get_media_player().is_playing and self.is_enabled():
                self._ensure_bpm()
        except Exception:
            pass

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

    def stop_show(self):
        """Stoppt die Auto-Show-Funktionen (zuletzt gestartete + aktuell konfigurierte)."""
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
            bm.set_bpm(bpm)
        except Exception as e:
            print(f"[MusicShowDirector] bpm error: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────────

_director: MusicShowDirector | None = None


def get_music_director() -> MusicShowDirector:
    global _director
    if _director is None:
        _director = MusicShowDirector()
    return _director
