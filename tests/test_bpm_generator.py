"""Tests fuer die BPM-Generator-Verdrahtung (Feature 3):

- Track persistiert die bpm_timeline (round-trip, Alt-Shows bleiben schlank).
- MusicShowDirector treibt die globale BPM aus der Timeline ueber die Position.
- Generator-View konstruiert sauber (offscreen).
"""
from __future__ import annotations
import pytest

from src.core.audio.media_player import Track, get_media_player
from src.core.engine.bpm_manager import get_bpm_manager, BpmMode


# ── Track-Persistenz ──────────────────────────────────────────────────────────

def test_track_timeline_roundtrip():
    tl = {"v": 1, "duration_ms": 2000, "step_ms": 2000, "window_ms": 8000,
          "segments": [[0, 120.0, 0.9], [1000, 128.0, 0.8]]}
    t = Track(path="song.mp3", bpm_timeline=tl, bpm_source="analysis")
    d = t.to_dict()
    assert "bpm_timeline" in d
    t2 = Track.from_dict(d)
    assert t2.bpm_source == "analysis"
    assert t2.bpm_timeline["segments"] == [[0, 120.0, 0.9], [1000, 128.0, 0.8]]


def test_track_without_timeline_stays_slim():
    t = Track(path="plain.mp3")
    assert "bpm_timeline" not in t.to_dict()       # Alt-Shows nicht aufblaehen
    t2 = Track.from_dict({"path": "x.mp3"})         # fehlendes Feld -> leeres dict
    assert t2.bpm_timeline == {}


def test_track_timeline_defensive_from_dict():
    t = Track.from_dict({"path": "x.mp3", "bpm_timeline": "kaputt"})
    assert t.bpm_timeline == {}                     # nicht-dict -> verworfen


# ── MusicShowDirector treibt BPM aus der Timeline ─────────────────────────────

def test_director_timeline_drives_bpm():
    from src.core.audio.music_show import MusicShowDirector
    mgr = get_bpm_manager()
    mgr.reset()
    mgr._audio_active = False
    mgr.set_locked(False)
    mgr.set_mode(BpmMode.AUTO)

    mp = get_media_player()
    tl = {"v": 1, "duration_ms": 20000,
          "segments": [[0, 120.0, 0.9], [10000, 140.0, 0.9]]}
    mp.set_tracks([Track(path="song.mp3", bpm_timeline=tl)])
    mp.couple_bpm = True

    d = MusicShowDirector()
    d._on_position(300, 20000)
    assert abs(mgr.bpm - 120.0) < 1.0
    assert mgr.current_source == "timeline"

    d._on_position(10000, 20000)
    assert abs(mgr.bpm - 140.0) < 1.0

    # Aufraeumen
    mp.set_tracks([])
    mgr.reset()


def test_director_timeline_yields_to_manual():
    """MANUAL/Lock haben Vorrang — die Timeline ueberschreibt nicht."""
    from src.core.audio.music_show import MusicShowDirector
    mgr = get_bpm_manager()
    mgr.reset()
    mgr._audio_active = False
    mgr.set_manual_bpm(100.0)          # -> MANUAL
    assert mgr.mode == BpmMode.MANUAL

    mp = get_media_player()
    tl = {"v": 1, "duration_ms": 20000, "segments": [[0, 140.0, 0.9]]}
    mp.set_tracks([Track(path="song.mp3", bpm_timeline=tl)])
    mp.couple_bpm = True

    d = MusicShowDirector()
    d._on_position(300, 20000)
    assert abs(mgr.bpm - 100.0) < 1.0   # MANUAL bleibt

    mp.set_tracks([])
    mgr.reset()
    mgr.set_mode(BpmMode.AUTO)


def test_director_no_timeline_no_drive():
    from src.core.audio.music_show import MusicShowDirector
    mgr = get_bpm_manager()
    mgr.reset()
    mgr._audio_active = False
    mgr.set_mode(BpmMode.AUTO)
    mp = get_media_player()
    mp.set_tracks([Track(path="plain.mp3")])   # keine Timeline
    mp.couple_bpm = True
    d = MusicShowDirector()
    d._on_position(5000, 20000)
    assert mgr.bpm == 0.0                       # nichts gesetzt
    mp.set_tracks([])
    mgr.reset()


# ── View-Konstruktion (offscreen) ─────────────────────────────────────────────

def test_generator_view_constructs():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.ui.views.bpm_generator_view import BpmGeneratorView
    v = BpmGeneratorView()
    assert v is not None
    # leere Timeline -> kein Crash beim Plot-Setzen / Summary
    v._on_analyzed(None)
    v.deleteLater()
    app.processEvents()


def test_generator_auto_suggestion():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.ui.views.bpm_generator_view import BpmGeneratorView
    from src.core.audio.offline_timeline import BpmTimeline, BpmSegment
    v = BpmGeneratorView()
    # Dateiname-Stichwort + Tempo → Genre-Vorschlag; echte Downbeats → Taktart
    v._path = "Some Hardstyle Anthem.mp3"
    tl = BpmTimeline(segments=[BpmSegment(0, 150.0, 0.9)],
                     beats_ms=[0, 400, 800, 1200], downbeats_ms=[0, 1200],
                     engine="beatthis", beats_per_bar=4, duration_ms=20000)
    v._update_suggestion(tl)
    assert v._sugg_genre == "hardstyle"
    assert "150" in v._lbl_suggest.text()
    assert v._taktart_bpb() == 4
    v.deleteLater()
    app.processEvents()


# ── Phase 2: taktgenaue Beat-Wiedergabe (Grid-Quelle) ─────────────────────────

def test_grid_source_emits_beats_only_when_active():
    mgr = get_bpm_manager()
    mgr.reset()
    mgr._audio_active = False
    mgr.set_locked(False)
    mgr.set_mode(BpmMode.AUTO)
    beats = []
    cb = lambda i: beats.append(i)
    mgr.subscribe_beat(cb)
    try:
        # ohne Grid-Quelle: emit_grid_beat tut nichts
        mgr.emit_grid_beat()
        assert beats == []
        # Grid aktivieren → Timer pausiert, emit feuert
        mgr.use_grid_source(True)
        assert mgr.grid_active is True
        assert mgr._grid_is_emitter() is True
        assert mgr._running is False
        mgr.emit_grid_beat()
        mgr.emit_grid_beat()
        assert len(beats) == 2
        # deaktivieren → emit feuert nicht mehr
        mgr.use_grid_source(False)
        mgr.emit_grid_beat()
        assert len(beats) == 2
    finally:
        mgr.unsubscribe_beat(cb)
        mgr.use_grid_source(False)
        mgr.reset()


def test_grid_downbeat_realigns_bar():
    mgr = get_bpm_manager()
    mgr.reset()
    mgr.set_mode(BpmMode.AUTO)
    mgr.set_beats_per_bar(4)
    mgr.use_grid_source(True)
    mgr.emit_grid_beat()        # idx0 (bar)
    mgr.emit_grid_beat()        # idx1
    bars = []
    cb = lambda b: bars.append(b)
    mgr.subscribe_bar(cb)
    try:
        mgr.emit_grid_beat(is_downbeat=True)   # richtet Index auf Downbeat aus → Bar
        assert len(bars) == 1
    finally:
        mgr.unsubscribe_bar(cb)
        mgr.use_grid_source(False)
        mgr.set_beats_per_bar(4)
        mgr.reset()


def test_grid_driver_fires_crossed_beats():
    """Der schnelle Timer feuert alle bis zur geschätzten Position fälligen Beats."""
    import time
    from src.core.audio.music_show import MusicShowDirector
    mgr = get_bpm_manager()
    mgr.reset()
    mgr.set_mode(BpmMode.AUTO)
    mgr._audio_active = False
    mgr.set_locked(False)
    mgr.use_grid_source(True)
    beats = []
    cb = lambda i: beats.append(i)
    mgr.subscribe_beat(cb)
    try:
        from src.core.audio.offline_timeline import BpmTimeline
        tl = BpmTimeline(beats_ms=[0, 500, 1000, 1500],
                         downbeats_ms=[0, 1000], beats_per_bar=4)
        d = MusicShowDirector()
        d._grid_arm(tl, 0)                          # Anker bei 0 → next_i zeigt auf Beat 500
        assert d._grid_next_i == 1
        d._grid_anchor_wall = time.monotonic() - 1.1   # 1.1 s vergangen → est ≈ 1100 ms
        d._grid_tick()
        assert len(beats) == 2        # Beats bei 500/1000 gekreuzt, 1500 noch nicht
        assert d._grid_next_i == 3
    finally:
        mgr.unsubscribe_beat(cb)
        mgr.use_grid_source(False)
        mgr.reset()
