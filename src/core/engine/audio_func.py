"""AudioFunction — spielt eine Audio-Datei ab, getriggert wie eine Cue.

Verwendet QMediaPlayer + QAudioOutput aus PySide6.QtMultimedia, wenn verfuegbar.
Wenn QtMultimedia nicht installiert ist, gibt es einen Fallback der den Pfad protokolliert.
"""
from __future__ import annotations
import os
import time
from .function import Function, FunctionType


class AudioFunction(Function):
    """Spielt eine Audio-Datei ab."""

    function_type = FunctionType.Audio

    def __init__(self, name: str = "Neues Audio", fid: int | None = None):
        super().__init__(name, fid)
        self.file_path: str = ""
        self.volume: float = 1.0          # 0.0–1.0
        self.loop: bool = False
        self.fade_in: float = 0.0
        self.fade_out: float = 0.0
        self._player = None
        self._audio_out = None
        self._available: bool = self._try_import_qt()
        # Fade-Rampen-State
        self._fade_timer = None
        self._fade_start_time: float = 0.0
        self._fade_from: float = 0.0
        self._fade_to: float = 0.0
        self._fade_duration: float = 0.0
        self._fade_kind: str = ""  # "in" | "out" | ""

    # ── Setup ────────────────────────────────────────────────────────────────

    def _try_import_qt(self) -> bool:
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput  # noqa: F401
            return True
        except Exception as e:
            print(f"[AudioFunction] QtMultimedia nicht verfuegbar: {e}")
            return False

    def _create_player(self):
        if self._player is not None:
            return
        if not self._available:
            return
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PySide6.QtCore import QUrl
        self._player = QMediaPlayer()
        self._audio_out = QAudioOutput()
        self._player.setAudioOutput(self._audio_out)
        # Loop handling
        try:
            self._player.mediaStatusChanged.connect(self._on_media_status)
        except Exception:
            pass

    def _on_media_status(self, status):
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                if self.loop:
                    self._player.setPosition(0)
                    self._player.play()
                else:
                    self.stop()
        except Exception:
            pass

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def _on_start(self):
        if not self.file_path or not os.path.exists(self.file_path):
            print(f"[AudioFunction] Datei fehlt: {self.file_path!r}")
            self._running = False
            return
        if not self._available:
            print(f"[AudioFunction] (mock) play {self.file_path}")
            return
        self._create_player()
        try:
            from PySide6.QtCore import QUrl
            self._player.setSource(QUrl.fromLocalFile(os.path.abspath(self.file_path)))
            # Fade-In: Lautstaerke 0 -> volume ueber fade_in Sekunden
            if self.fade_in > 0.0:
                self._audio_out.setVolume(0.0)
                self._start_fade(0.0, self.volume, self.fade_in, kind="in")
            else:
                self._audio_out.setVolume(self.volume)
            self._player.play()
        except Exception as e:
            print(f"[AudioFunction] play error: {e}")

    def _on_stop(self):
        # Fade-Out: wenn fade_out > 0 und Player laeuft, sanft ausblenden
        if (self._player is not None and self._audio_out is not None
                and self.fade_out > 0.0 and self._available):
            try:
                cur = float(self._audio_out.volume())
                if cur > 0.001:
                    self._start_fade(cur, 0.0, self.fade_out, kind="out")
                    return
            except Exception as e:
                print(f"[AudioFunction] fade out error: {e}")
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass
        self._cancel_fade()

    # ── Fade-Rampe ───────────────────────────────────────────────────────────

    def _start_fade(self, from_vol: float, to_vol: float, duration: float,
                    kind: str):
        if not self._available or self._audio_out is None:
            return
        try:
            from PySide6.QtCore import QTimer
        except Exception:
            return
        self._cancel_fade()
        self._fade_from = max(0.0, min(1.0, from_vol))
        self._fade_to = max(0.0, min(1.0, to_vol))
        self._fade_duration = max(0.01, float(duration))
        self._fade_start_time = time.monotonic()
        self._fade_kind = kind
        self._fade_timer = QTimer()
        self._fade_timer.setInterval(30)
        self._fade_timer.timeout.connect(self._fade_step)
        self._fade_timer.start()

    def _fade_step(self):
        if self._audio_out is None or self._fade_timer is None:
            return
        elapsed = time.monotonic() - self._fade_start_time
        t = min(1.0, elapsed / self._fade_duration)
        vol = self._fade_from + (self._fade_to - self._fade_from) * t
        try:
            self._audio_out.setVolume(vol)
        except Exception:
            pass
        if t >= 1.0:
            done_kind = self._fade_kind
            self._cancel_fade()
            if done_kind == "out" and self._player is not None:
                try:
                    self._player.stop()
                except Exception:
                    pass

    def _cancel_fade(self):
        if self._fade_timer is not None:
            try:
                self._fade_timer.stop()
            except Exception:
                pass
            self._fade_timer = None
        self._fade_kind = ""

    # ── Tick (nicht-DMX) ─────────────────────────────────────────────────────

    def write(self, universes, patch_cache, dt, function_registry=None):
        # Audio braucht keinen DMX-Output, aber wir aktualisieren elapsed/Auto-Stop
        self._elapsed += dt
        # Falls QtMultimedia nicht verfuegbar, stoppe nach kuenstlicher Dauer
        if not self._available and self._elapsed > 1.0:
            self.stop()

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "file_path": self.file_path,
            "volume": self.volume,
            "loop": self.loop,
            "fade_in": self.fade_in,
            "fade_out": self.fade_out,
        })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AudioFunction":
        af = cls(name=d.get("name", "Audio"), fid=d.get("id"))
        af.file_path = d.get("file_path", "")
        af.volume = float(d.get("volume", 1.0))
        af.loop = bool(d.get("loop", False))
        af.fade_in = float(d.get("fade_in", 0.0))
        af.fade_out = float(d.get("fade_out", 0.0))
        return af
