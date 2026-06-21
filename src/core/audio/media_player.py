"""MediaPlayer — In-App-Wiedergabe von Musikdateien (MP3/MP4) + Playlist.

Komfort-Player INNERHALB von LightOS: spielt die Lieder einer Playlist ab und liefert
„aktuelles / nächstes Lied" an die UI und die Virtuelle Konsole (VCSongInfo).

BPM-Quelle: PRIMÄR VirtualDJ → OS2L. ``src/core/audio/os2l.py`` füttert den globalen
``BPMManager`` bei jedem Beat-Event automatisch. Dieser Player setzt beim Trackwechsel nur
eine grobe **Nominal-BPM als Fallback** (``couple_bpm``) — sobald OS2L läuft (VirtualDJ
sendet Beats), wird die echte BPM kontinuierlich nachgeschoben und überschreibt sie.

Der echte ``QMediaPlayer`` wird LAZY erst beim ersten Abspielen erzeugt; Playlist-Logik
(set/next/prev/current/next_track) funktioniert ohne Audio-Backend (headless/Test-tauglich).
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal


AUDIO_EXTS = (".mp3", ".mp4", ".m4a", ".wav", ".flac", ".aac", ".ogg")


# ── Track ───────────────────────────────────────────────────────────────────────

@dataclass
class Track:
    path: str
    title: str = ""
    genre: str = ""
    bpm: float = 0.0
    # F-15: Herkunft der BPM — "guess" (Dateiname), "tag" (eingebettetes ID3/MP4-Tag),
    # "analysis" (Offline-numpy-Analyse). Nur Info/Anzeige, kein Verhalten.
    bpm_source: str = "guess"
    # AUTODJ-(a): Funktions-IDs der „Per-Song-Look"-Auto-Show für diesen Track.
    autoshow_function_ids: list[int] = field(default_factory=list)
    # BPM-Generator: zeitgestützte BPM-Kurve (Offline-Analyse) als kompaktes
    # BpmTimeline.to_dict() ({} = keine). Treibt beim Abspielen die BPM über die
    # Wiedergabe-Position (MusicShowDirector → request_bpm("timeline")).
    bpm_timeline: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.title:
            self.title = clean_title(self.path)

    def to_dict(self) -> dict:
        d = {
            "path": self.path,
            "title": self.title,
            "genre": self.genre,
            "bpm": self.bpm,
            "bpm_source": self.bpm_source,
            "autoshow_function_ids": [int(x) for x in self.autoshow_function_ids],
        }
        if self.bpm_timeline:   # nur wenn vorhanden — Alt-Shows bleiben schlank
            d["bpm_timeline"] = self.bpm_timeline
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Track":
        ids = []
        for x in d.get("autoshow_function_ids", []) or []:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                pass
        tl = d.get("bpm_timeline") or {}
        if not isinstance(tl, dict):
            tl = {}
        return cls(
            path=str(d.get("path", "")),
            title=str(d.get("title", "") or ""),
            genre=str(d.get("genre", "") or ""),
            bpm=float(d.get("bpm", 0) or 0),
            bpm_source=str(d.get("bpm_source", "guess") or "guess"),
            autoshow_function_ids=ids,
            bpm_timeline=tl,
        )


# ── BPM-/Genre-Heuristik (keine Offline-Analyse verfügbar) ──────────────────────

def clean_title(path: str) -> str:
    """Lesbarer Titel aus dem Dateinamen: Endung, „- Kopie", „(1)" usw. entfernen."""
    name = os.path.splitext(os.path.basename(path))[0]
    name = re.sub(r"\s*-\s*Kopie", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*\(\d+\)\s*$", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or os.path.basename(path)


def guess_genre_bpm(name: str) -> tuple[str, float]:
    """Grobe (Genre, BPM)-Schätzung aus dem Dateinamen.

    Ersetzt keine echte Analyse — dient als Effekt-Takt-Vorgabe / Fallback, bis die
    echte BPM via VirtualDJ→OS2L (oder Audio-Beat-Erkennung) übernimmt.
    """
    low = name.lower()
    # Frenchcore: oft eine explizite BPM in [..] im Titel (z. B. "[205]").
    if "frenchcore" in low or "frenchcord" in low:
        m = re.search(r"\[(\d{2,3})\]", name)
        return "Frenchcore", float(m.group(1)) if m else 185.0
    if "hardstyle" in low or "hardtekk" in low or "rawphoric" in low or "rawkicks" in low:
        return "Hardstyle", 150.0
    if "hypertechno" in low:
        return "Hypertechno", 150.0
    if "psy-bounce" in low or "psy bounce" in low:
        return "Psy-Bounce", 150.0
    if "hbz" in low or "bounce" in low:
        return "Bounce", 155.0
    if "techno" in low:
        return "Techno", 135.0
    return "Dance", 128.0


# ── MediaPlayer ─────────────────────────────────────────────────────────────────

class MediaPlayer(QObject):
    """Schlanker Playlist-Player. Audio-Backend (QMediaPlayer) wird lazy erzeugt."""

    trackChanged = Signal(int)            # neuer Playlist-Index (-1 = leer)
    playingChanged = Signal(bool)         # True = spielt gerade
    positionChanged = Signal(int, int)    # (Position ms, Dauer ms)
    playlistChanged = Signal()            # Playlist neu gesetzt

    def __init__(self):
        super().__init__()
        self.tracks: list[Track] = []
        self.index: int = -1
        self.couple_bpm: bool = True       # Nominal-BPM als Fallback an Lichter koppeln
        self._volume: int = 80             # 0..100
        self._player = None                # QMediaPlayer (lazy)
        self._audio = None                 # QAudioOutput (lazy)
        self._playing = False

    # ── Playlist ────────────────────────────────────────────────────────────────

    def set_tracks(self, tracks: list[Track]):
        self.tracks = list(tracks)
        self.index = 0 if self.tracks else -1
        self.playlistChanged.emit()
        self.trackChanged.emit(self.index)

    def set_playlist_dicts(self, dicts: list[dict]):
        self.set_tracks([Track.from_dict(d) for d in (dicts or [])])

    def to_dicts(self) -> list[dict]:
        return [t.to_dict() for t in self.tracks]

    def load_paths(self, paths: list[str]):
        """Erzeugt Tracks aus Dateipfaden. BPM: eingebettetes Tag (F-15) schlägt die
        Dateinamen-Schätzung; sonst Genre/BPM aus dem Namen geraten."""
        out: list[Track] = []
        for p in paths:
            title = clean_title(p)
            genre, bpm = guess_genre_bpm(os.path.basename(p))
            source = "guess"
            try:
                from src.core.audio.tag_reader import read_tag_bpm
                tb = read_tag_bpm(p)
                if tb > 0:
                    bpm, source = tb, "tag"
            except Exception:
                pass
            out.append(Track(path=p, title=title, genre=genre,
                             bpm=bpm, bpm_source=source))
        self.set_tracks(out)

    def refine_bpm_from_tags(self) -> int:
        """F-15: BPM aller Tracks aus eingebetteten Tags nachziehen (Tag schlägt die
        Schätzung). Setzt NUR ``Track.bpm``/``bpm_source`` — greift NICHT in den
        BPM-Manager ein (OS2L/Audio bleiben Vorrang). Liefert die Anzahl Änderungen."""
        try:
            from src.core.audio.tag_reader import read_tag_bpm
        except Exception:
            return 0
        changed = 0
        for t in self.tracks:
            try:
                tb = read_tag_bpm(t.path)
            except Exception:
                tb = 0.0
            if tb > 0 and (t.bpm_source != "tag" or abs(t.bpm - tb) > 0.001):
                t.bpm, t.bpm_source = tb, "tag"
                changed += 1
        if changed:
            self.playlistChanged.emit()
        return changed

    def load_folder(self, folder: str):
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            names = []
        paths = [os.path.join(folder, n) for n in names
                 if n.lower().endswith(AUDIO_EXTS)]
        self.load_paths(paths)

    # ── Aktuelles / nächstes Lied ─────────────────────────────────────────────────

    @property
    def current_track(self) -> Track | None:
        if 0 <= self.index < len(self.tracks):
            return self.tracks[self.index]
        return None

    @property
    def next_track(self) -> Track | None:
        if not self.tracks:
            return None
        return self.tracks[(self.index + 1) % len(self.tracks)]

    @property
    def is_playing(self) -> bool:
        return self._playing

    # ── Transport ────────────────────────────────────────────────────────────────

    def play_index(self, i: int):
        if not self.tracks:
            return
        self.index = i % len(self.tracks)
        self.trackChanged.emit(self.index)
        self._apply_track_bpm()
        self._start_current()

    def play(self):
        if self.index < 0 and self.tracks:
            self.index = 0
            self.trackChanged.emit(self.index)
            self._apply_track_bpm()
        if self._player is None:
            self._start_current()
        elif self._ensure_player():
            self._player.play()
            self._set_playing(True)

    def pause(self):
        if self._player is not None:
            self._player.pause()
        self._set_playing(False)

    def toggle(self):
        if self._playing:
            self.pause()
        else:
            self.play()

    def stop(self):
        if self._player is not None:
            self._player.stop()
        self._set_playing(False)

    def next(self):
        if self.tracks:
            self.play_index(self.index + 1)

    def prev(self):
        if self.tracks:
            self.play_index(self.index - 1)

    def seek(self, ms: int):
        if self._player is not None:
            try:
                self._player.setPosition(int(ms))
            except Exception:
                pass

    def set_volume(self, vol: int):
        self._volume = max(0, min(100, int(vol)))
        if self._audio is not None:
            self._audio.setVolume(self._volume / 100.0)

    def volume(self) -> int:
        return self._volume

    # ── Audio-Backend (lazy) ──────────────────────────────────────────────────────

    def _ensure_player(self) -> bool:
        """Erzeugt QMediaPlayer/QAudioOutput beim ersten Bedarf. False = nicht verfügbar."""
        if self._player is not None:
            return True
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._audio = QAudioOutput()
            self._audio.setVolume(self._volume / 100.0)
            self._player = QMediaPlayer()
            self._player.setAudioOutput(self._audio)
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration)
            self._player.mediaStatusChanged.connect(self._on_status)
            self._player.playbackStateChanged.connect(self._on_state)
            return True
        except Exception as e:
            print(f"[MediaPlayer] Audio-Backend nicht verfügbar: {e}")
            self._player = None
            self._audio = None
            return False

    def _start_current(self):
        t = self.current_track
        if t is None:
            return
        if not self._ensure_player():
            return
        try:
            from PySide6.QtCore import QUrl
            self._player.setSource(QUrl.fromLocalFile(t.path))
            self._player.play()
            self._set_playing(True)
        except Exception as e:
            print(f"[MediaPlayer] Abspielen fehlgeschlagen ({t.path}): {e}")

    def _apply_track_bpm(self):
        """Nominal-BPM des aktuellen Tracks als FALLBACK setzen (OS2L hat Vorrang)."""
        if not self.couple_bpm:
            return
        t = self.current_track
        if t is None or t.bpm <= 0:
            return
        try:
            from src.core.audio.os2l import get_os2l_server
            srv = get_os2l_server()
            if srv.is_running() and srv.last_bpm() > 0:
                return   # VirtualDJ liefert echte BPM — nicht überschreiben
        except Exception:
            pass
        try:
            from src.core.engine.bpm_manager import get_bpm_manager
            mgr = get_bpm_manager()
            if not mgr.audio_active:
                mgr.request_bpm(t.bpm, "file")
        except Exception as e:
            print(f"[MediaPlayer] BPM-Kopplung Fehler: {e}")

    def _set_playing(self, playing: bool):
        if playing != self._playing:
            self._playing = playing
            self.playingChanged.emit(playing)

    # ── QMediaPlayer-Callbacks ─────────────────────────────────────────────────────

    def _on_position(self, pos: int):
        dur = self._player.duration() if self._player is not None else 0
        self.positionChanged.emit(int(pos), int(dur))

    def _on_duration(self, dur: int):
        pos = self._player.position() if self._player is not None else 0
        self.positionChanged.emit(int(pos), int(dur))

    def _on_status(self, status):
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                self.next()   # Auto-Advance zum nächsten Lied
        except Exception:
            pass

    def _on_state(self, state):
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            self._set_playing(state == QMediaPlayer.PlaybackState.PlayingState)
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────────

_player: MediaPlayer | None = None


def get_media_player() -> MediaPlayer:
    global _player
    if _player is None:
        _player = MediaPlayer()
    return _player
